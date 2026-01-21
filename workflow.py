import os
import json
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import time
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import PyPDF2
from docx import Document
import openpyxl
from langchain_groq import ChatGroq

# LOGGING
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drive_organizer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# CONFIGURATION
SCOPES = ['https://www.googleapis.com/auth/drive']

CATEGORIES = [
    "HR",
    "Finance",
    "Academics",
    "Projects",
    "Marketing",
    "Personal",
    "Miscellaneous"
]

CONFIDENCE_THRESHOLD = 0.7
MAX_CONTENT_LENGTH = 3000

#MIME TYPES TO SKIP
SKIP_MIME_PREFIXES = (
    "image/",
    "video/"
)

# DATA MODELS
@dataclass
class FileInfo:
    id: str
    name: str
    mime_type: str
    size: int
    created_time: str
    parents: List[str]


@dataclass
class Classification:
    category: str
    confidence: float
    reasoning: str
    subcategory: Optional[str] = None


# GOOGLE DRIVE CLIENT
class GoogleDriveClient:
    """Handles Google Drive API operations"""

    def __init__(self, credentials_path: str):
        self.credentials_path = credentials_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        creds = None

        if os.path.exists("token.pickle"):
            with open("token.pickle", "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open("token.pickle", "wb") as token:
                pickle.dump(creds, token)

        self.service = build("drive", "v3", credentials=creds)
        logger.info("Authenticated with Google Drive")

    def list_files(self, folder_id: str = "root") -> List[FileInfo]:
        files = []
        page_token = None

        while True:
            response = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, size, createdTime, parents)",
                pageToken=page_token
            ).execute()

            for file in response.get("files", []):
                files.append(FileInfo(
                    id=file["id"],
                    name=file["name"],
                    mime_type=file["mimeType"],
                    size=int(file.get("size", 0)),
                    created_time=file["createdTime"],
                    parents=file.get("parents", [])
                ))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return files

    def create_folder(self, folder_name: str, parent_id: str = "root") -> Optional[str]:
        query = (
            f"name='{folder_name}' "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )

        response = self.service.files().list(q=query, fields="files(id)").execute()
        folders = response.get("files", [])

        if folders:
            return folders[0]["id"]

        folder = self.service.files().create(
            body={
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]
            },
            fields="id"
        ).execute()

        return folder["id"]

    def move_file(self, file_id: str, folder_id: str):
        file = self.service.files().get(
            fileId=file_id, fields="parents"
        ).execute()

        previous_parents = ",".join(file.get("parents", []))

        self.service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents"
        ).execute()

    def download_file_content(self, file_id: str, mime_type: str) -> Optional[bytes]:
        if "google-apps" in mime_type:
            request = self.service.files().export_media(
                fileId=file_id,
                mimeType="text/plain"
            )
        else:
            request = self.service.files().get_media(fileId=file_id)

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        return buffer.getvalue()


# CONTENT EXTRACTION
class ContentExtractor:

    @staticmethod
    def extract(content: bytes, mime_type: str, filename: str) -> str:
        try:
            if "pdf" in mime_type:
                return ContentExtractor._from_pdf(content)
            elif "word" in mime_type or "document" in mime_type:
                return ContentExtractor._from_docx(content)
            elif "sheet" in mime_type or "excel" in mime_type:
                return ContentExtractor._from_excel(content)
            elif "text" in mime_type:
                return content.decode("utf-8", errors="ignore")
            else:
                return f"Filename: {filename}"
        except Exception:
            return f"Filename: {filename}"

    @staticmethod
    def _from_pdf(content: bytes) -> str:
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages[:5]:
            text += page.extract_text() or ""
        return text[:MAX_CONTENT_LENGTH]

    @staticmethod
    def _from_docx(content: bytes) -> str:
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)[:MAX_CONTENT_LENGTH]

    @staticmethod
    def _from_excel(content: bytes) -> str:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        sheet = wb.active
        text = " ".join(
            str(cell.value) for row in sheet.iter_rows(max_row=20)
            for cell in row if cell.value
        )
        return text[:MAX_CONTENT_LENGTH]



# AI CLASSIFIER (LLAMA VIA GROQ)
class AIClassifier:

    def __init__(self, api_key: str):
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            groq_api_key=api_key,
            temperature=0
        )

    def classify(self, file: FileInfo, content: str) -> Classification:
        prompt = self._prompt(file, content)
        response = self.llm.invoke(prompt).content.strip()
        response = response.strip("```json").strip("```")
        result = json.loads(response)

        return Classification(
            category=result["category"],
            confidence=float(result["confidence"]),
            reasoning=result["reasoning"],
            subcategory=result.get("subcategory")
        )

    def _prompt(self, file: FileInfo, content: str) -> str:
        return f"""
Classify this file into ONE category from:
{', '.join(CATEGORIES)}

File name: {file.name}
Type: {file.mime_type}
Size: {file.size} bytes

Content:
{content[:MAX_CONTENT_LENGTH]}

Return ONLY valid JSON:
{{
  "category": "...",
  "confidence": 0.0-1.0,
  "reasoning": "...",
  "subcategory": "optional"
}}
"""



# DRIVE ORGANIZER
class DriveOrganizer:

    def __init__(self, credentials_path: str, groq_api_key: str):
        self.drive = GoogleDriveClient(credentials_path)
        self.classifier = AIClassifier(groq_api_key)
        self.folders: Dict[str, str] = {}
    def _should_skip_file(self, file: FileInfo) -> bool:
        if file.mime_type == "application/vnd.google-apps.folder":
            return True
        for prefix in SKIP_MIME_PREFIXES:
            if file.mime_type.startswith(prefix):
                return True
        return False

    def organize(self, root="root", dry_run=False):
        for category in CATEGORIES + ["Needs Review"]:
            self.folders[category] = self.drive.create_folder(category, root)

        files = self.drive.list_files(root)

        for file in files:

            if self._should_skip_file(file):
                logger.info(f"Skipping: {file.name} ({file.mime_type})")
                continue

            content_bytes = self.drive.download_file_content(file.id, file.mime_type)
            content = ContentExtractor.extract(content_bytes, file.mime_type, file.name)

            classification = self.classifier.classify(file, content)

            destination = (
                classification.category
                if classification.confidence >= CONFIDENCE_THRESHOLD
                else "Needs Review"
            )

            if not dry_run:
                self.drive.move_file(file.id, self.folders[destination])
                logger.info(f"Moved '{file.name}' → {destination}")
            else:
                logger.info(f"[DRY RUN] '{file.name}' → {destination}")

            time.sleep(0.5)


# MAIN
if __name__ == "__main__":

    CREDENTIALS_FILE = "/Users/akshitagrawal/Desktop/datasets/assignment3/credentials.json"
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    organizer = DriveOrganizer(CREDENTIALS_FILE, GROQ_API_KEY)

    mode = input("Run mode (1=dry, 2=live): ").strip()
    organizer.organize(dry_run=(mode == "1"))
