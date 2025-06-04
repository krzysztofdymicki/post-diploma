# Sentiment Analysis Information Gathering System

This system automates the discovery, verification, and categorization of online information relevant to a bachelor's thesis on sentiment analysis.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your Google Gemini API key
   ```

3. **Test the setup:**
   ```bash
   python test_setup.py
   ```

## Project Structure

```
post-diploma/
├── src/                    # Source code
│   ├── config.py          # Configuration management
│   ├── database.py        # Database operations
│   ├── gemini_client.py   # Gemini API integration
│   └── ...               # Other modules (to be added)
├── data/                  # Database and data files
├── logs/                  # Log files
├── tests/                 # Unit tests
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
└── test_setup.py         # Setup verification script
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

- `GEMINI_API_KEY`: Your Google Gemini API key (get from [Google AI Studio](https://makersuite.google.com/app/apikey))
- `DATABASE_PATH`: Path to SQLite database file
- `MAX_CONTENT_LENGTH`: Maximum content length to process
- Other settings as needed

## Development Phases

### Phase 1: Foundation ✅
- [x] Project structure
- [x] Database schema
- [x] Configuration management
- [x] Gemini API integration
- [x] Basic testing

### Phase 2: Data Collection (Next)
- [ ] Search module implementation
- [ ] Content acquisition
- [ ] Deduplication logic

### Phase 3: AI Analysis
- [ ] Content relevance verification
- [ ] Credibility assessment
- [ ] Categorization and extraction

### Phase 4: Integration
- [ ] Full workflow orchestration
- [ ] Error handling and logging
- [ ] Results export

## API Keys and Setup

1. **Google Gemini API:**
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Create a new API key
   - Add it to your `.env` file as `GEMINI_API_KEY`

## Database Schema

The system uses SQLite with the following main tables:
- `search_queries`: Search terms and topics
- `web_resources`: Discovered URLs and metadata
- `content`: Fetched and cleaned content
- `analysis_results`: AI analysis results
- `categorization`: Final categorization and tags

## Usage

After setup, you can run individual modules or the full pipeline:

```python
from src.database import DatabaseManager
from src.gemini_client import GeminiClient

# Initialize components
db = DatabaseManager("./data/sentiment_analysis.db")
gemini = GeminiClient()

# Test API connection
if gemini.test_connection():
    print("Gemini API is working!")
```

## Next Steps

1. Run `python test_setup.py` to verify installation
2. Implement search and content acquisition modules
3. Start with small-scale testing on sentiment analysis topics