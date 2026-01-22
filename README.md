# AI-Powered Google Drive Organizer

An intelligent document management system that automatically classifies and organizes files in Google Drive using AI, supporting both one-time batch processing and real-time auto-organization via webhooks.

## System Design

The system follows a modular architecture with four core components:

1. **Google Drive Client** - Handles authentication, file operations (list, download, move), and folder management using the Google Drive API
2. **Content Extractor** - Extracts text content from various file formats (PDF, DOCX, XLSX, plain text) for analysis
3. **AI Classifier** - Uses LLM-based classification to categorize files with confidence scoring
4. **Webhook Server** - Flask-based server that listens for real-time Drive changes and triggers automatic organization

The workflow operates in two modes:
- **Batch Mode**: One-time processing of existing files (with dry-run option)
- **Real-time Mode**: Continuous monitoring via Google Drive push notifications

## AI Classification Approach

The system uses **Llama 3.3 70B** (via Groq API) for intelligent file classification:

### Classification Strategy
- **Prompt Engineering**: Provides file metadata (name, type, size) and content preview to the LLM
- **Structured Output**: Returns JSON with category, confidence score (0-1), reasoning, and optional subcategory
- **Confidence Threshold**: Files with confidence ≥ 0.7 are auto-organized; lower confidence files go to "Needs Review"
- **Context Limitation**: Uses first 3000 characters of content to stay within token limits

### Categories
- HR
- Finance
- Academics
- Projects
- Marketing
- Personal
- Miscellaneous
- Needs Review (low confidence)

## 🛠️ Tools & Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Google Drive API** | `googleapiclient` | File management and webhooks |
| **Authentication** | `google-auth-oauthlib` | OAuth2 credential flow |
| **AI Model** | Groq (Llama 3.3 70B) | File classification |
| **LLM Framework** | LangChain | LLM integration |
| **Document Parsing** | PyPDF2, python-docx, openpyxl | Content extraction |
| **Web Server** | Flask | Webhook endpoint |
| **Logging** | Python logging | Activity tracking |

## 📋 Sample Workflow

### Scenario: New Invoice Upload

```
1. USER ACTION
   └─ User uploads "Q4_2024_Invoice_Acme.pdf" to Drive root

2. WEBHOOK TRIGGER
   └─ Google Drive sends POST to /webhook/drive
   └─ System detects new file event

3. FILE PROCESSING
   └─ Download file content
   └─ Extract text from PDF:
       "INVOICE #12345
        Date: Dec 15, 2024
        Bill To: Acme Corp
        Amount Due: $5,234.50..."

4. AI CLASSIFICATION
   └─ Send to Llama 3.3 with prompt:
       "File name: Q4_2024_Invoice_Acme.pdf
        Content: INVOICE #12345..."
   └─ Receives response:
       {
         "category": "Finance",
         "confidence": 0.95,
         "reasoning": "Document is clearly an invoice with financial details",
         "subcategory": "Invoices"
       }

5. AUTO-ORGANIZATION
   └─ Confidence 0.95 ≥ 0.7 threshold ✓
   └─ Move file to /Finance/ folder
   └─ Log: "✓ Moved 'Q4_2024_Invoice_Acme.pdf' → Finance (confidence: 0.95)"

6. RESULT
   └─ File automatically organized without user intervention
```

## Pseudo code
```python
FUNCTION organize_file(file):
    # Step 1: Validation
    IF file.is_folder OR file.is_media OR file.already_organized:
        RETURN skip
    
    # Step 2: Content Extraction
    TRY:
        content_bytes = download_file(file.id)
        
        IF file.type == "PDF":
            content = extract_pdf_text(content_bytes)
        ELSE IF file.type == "DOCX":
            content = extract_docx_text(content_bytes)
        ELSE IF file.type == "XLSX":
            content = extract_excel_text(content_bytes)
        ELSE:
            content = extract_plain_text(content_bytes)
        
        content = truncate(content, MAX_LENGTH=3000)
    CATCH error:
        content = "Filename: " + file.name
    
    # Step 3: AI Classification
    prompt = build_classification_prompt(file, content)
    response = llm_api.invoke(prompt)
    classification = parse_json(response)
    
    # Step 4: Decision Making
    IF classification.confidence >= THRESHOLD (0.7):
        destination_folder = classification.category
    ELSE:
        destination_folder = "Needs Review"
    
    # Step 5: File Movement
    success = move_file_to_folder(file.id, destination_folder)
    
    # Step 6: Logging
    IF success:
        LOG("✓ Moved '" + file.name + "' → " + destination_folder)
        mark_as_organized(file.id)
        RETURN success
    ELSE:
        LOG("✗ Failed to move '" + file.name + "'")
        RETURN failure


FUNCTION batch_organize(folder_id):
    # Initialize
    setup_category_folders()
    files = list_all_files(folder_id)
    
    stats = {organized: 0, skipped: 0, errors: 0}
    
    # Process each file
    FOR EACH file IN files:
        result = organize_file(file)
        
        IF result == success:
            stats.organized += 1
        ELSE IF result == skip:
            stats.skipped += 1
        ELSE:
            stats.errors += 1
        
        sleep(0.5)  # Rate limiting
    
    print_summary(stats)


FUNCTION real_time_organize():
    # Setup
    setup_category_folders()
    subscribe_to_webhooks()
    start_flask_server()
    
    # Event loop
    WHILE server_running:
        WAIT FOR webhook_event
        
        IF event.type == "file_created" OR "file_updated":
            new_files = get_unorganized_files()
            
            FOR EACH file IN new_files:
                organize_file(file)
```               

## Limitations

### Current Limitations
1. **Media Files**: Images, videos, and audio files are skipped (no content extraction)
2. **Rate Limiting**: 0.5s delay between operations to avoid API throttling
3. **Content Size**: Limited to first 3000 characters per file
4. **Webhook Expiration**: Subscriptions expire after 7 days (requires renewal)
5. **HTTPS Requirement**: Webhooks require verified HTTPS domain
6. **Single Language**: Optimized for English content
7. **No Version Control**: Doesn't track file history or multiple versions
8. **Category Rigidity**: Predefined categories (no dynamic creation)

### Edge Cases
- Very large files may timeout during download
- Scanned PDFs without OCR won't be classified accurately
- Ambiguous files may require manual review
- Nested folder structures not fully supported

## Future Improvements

### Short-term Enhancements
- **Image Analysis**: Use vision models (GPT-4V, Claude) for image classification
- **Multi-language Support**: Add language detection and translation
- **Smart Subcategories**: Auto-generate subcategories based on content patterns
- **Duplicate Detection**: Identify and merge duplicate files

### Medium-term Features
- **Learning System**: Track user corrections to improve classification
- **Custom Rules**: Allow user-defined classification rules (e.g., "all .tax files → Finance")
- **Email Notifications**: Alert users about organized files
- **Web Dashboard**: Visual interface for reviewing and managing classifications

### Long-term Vision
- **Semantic Search**: Vector database for content-based file search
- **Auto-tagging**: Generate metadata tags for better organization
- **Smart Retention**: Suggest file archival/deletion based on usage patterns
- **Integration Hub**: Connect with Slack, Notion, Asana for context-aware classification
- **Mobile App**: iOS/Android apps for on-the-go file management

## 📦 Installation

```bash
# Clone repository
git clone <repository-url>
cd drive-organizer

# Install dependencies
pip install -r requirements.txt

# Set up credentials
# 1. Create Google Cloud project
# 2. Enable Google Drive API
# 3. Download credentials.json

# Set API key
export GROQ_API_KEY='your-groq-api-key'

# Run
python drive_organizer.py
```

**Note**: Ensure your Google Cloud project has Drive API enabled and webhook domain is verified in the Google Cloud Console for real-time mode.