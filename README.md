# Automated Academic Research Workflow System

## Overview

This project is an automated system designed to streamline the academic research process. It assists researchers by:

1.  **Generating focused search queries** from a general topic using AI.
2.  **Retrieving information** from both general internet sources and academic paper databases.
3.  **Assessing the quality** of found resources using AI based on relevance, credibility, and usefulness.
4.  **Filtering** results to highlight the most promising candidates.
5.  **Extracting and storing the full text content** of these high-quality resources.

The system is built with a modular Python architecture, uses an SQLite database for data persistence, and provides extensive logging and command-line options for flexible workflow execution.

## Features

-   **AI-Powered Query Generation:** Expands a broad topic into specific search terms.
-   **Multi-Source Information Retrieval:** Searches both the general web (e.g., via Tavily API) and academic databases (e.g., via Semantic Scholar API).
-   **AI-Driven Quality Assessment:** Evaluates resources for relevance, credibility, and usefulness using models like Google Gemini.
-   **Configurable Filtering:** Narrows down results to the top percentage from each source type.
-   **Content Extraction:** Fetches and parses text from HTML pages and PDF documents.
-   **Database Persistence:** Stores all queries, resources, assessments, and extracted content in an SQLite database.
-   **Deduplication:** Avoids redundant processing of identical queries and resources.
-   **Comprehensive Logging:** Tracks all operations, successes, and errors.
-   **Flexible CLI:** Allows running the full workflow or individual stages with various parameters.
-   **Reproducibility:** Saves detailed workflow results and configurations.

## Project Structure

```
post-diploma/
├── src/                    # Source code
│   ├── main.py             # Main workflow orchestrator and CLI
│   ├── database.py         # Database operations module
│   ├── query_agent.py      # AI-driven query generation
│   ├── internet_search_provider.py # Internet search integration
│   ├── research_papers_provider.py # Academic paper search integration
│   ├── quality_assessment_module.py # AI-driven quality assessment
│   ├── result_filtering_module.py # Filtering of assessed results
│   ├── browsing_agent.py   # Content extraction from web/PDFs
│   ├── main_part2.py       # Orchestration for content fetching
│   ├── gemini_client.py    # Client for Google Gemini API
│   ├── config.py           # Configuration management (loading .env)
│   └── ...                 # Other utility modules
├── data/                   # Default directory for database files (e.g., research_db.db)
│                           # Typically in .gitignore
├── logs/                   # Log files from workflow execution
│                           # Typically in .gitignore
├── outputs/                # Generated queries JSON, workflow results JSON
│                           # Typically in .gitignore
├── tests/                  # Unit and integration tests
├── requirements.txt        # Python package dependencies
├── .gitignore              # Specifies intentionally untracked files
├── .env.example            # Template for environment variables
├── .env                    # Local environment variables (should be in .gitignore)
├── README.md               # This file
└── OPIS_PROJEKTU.txt       # Detailed project description in Polish
```

## Installation and Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd post-diploma
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
    Edit the `.env` file and add your API keys and other configurations:
    -   `GEMINI_API_KEY`: Your Google Gemini API key.
    -   `TAVILY_API_KEY`: Your Tavily Search API key (or other relevant search API keys).
    -   `DATABASE_PATH`: Path to the SQLite database file (default: `data/research_db.db`).
    -   `LOG_LEVEL`: (Optional) Logging level, e.g., `INFO`, `DEBUG`.

## Usage (Command-Line Interface)

The main script for running the workflow is `src/main.py`.

### Running the Full Workflow

This command will generate queries (if a topic is provided and no query file), search, assess, filter, and fetch content.

```bash
python src/main.py --topic "Your Research Topic" --run-fetching [--clear-db] [other_options]
```

**Example:**

```bash
python src/main.py ^
  --topic "AI applications in renewable energy" ^
  --max-queries 5 ^
  --internet-filter-percent 15 ^
  --research-filter-percent 10 ^
  --run-fetching ^
  --clear-db
```
*(Note: `^` is the line continuation character for Windows Command Prompt. Use `\` for PowerShell or bash.)*

### Key CLI Options

-   `--topic <str>`: Initial research topic for query generation.
-   `--queries-file <Path>`: Use an existing JSON file of search queries.
-   `--db-path <str>`: Path to the SQLite database (default: `data/research_db.db`).
-   `--clear-db`: Clear the database before running. **Use with caution.**
-   `--max-queries <int>`: Limit the number of queries to process.
-   `--internet-only`: Use only internet search.
-   `--papers-only`: Use only academic paper search.
-   `--run-assessment`: Explicitly run quality assessment (useful as a standalone step).
    -   `--assessment-batch-size <int>`: Batch size for assessment.
-   `--run-filtering`: Explicitly run result filtering.
    -   `--internet-filter-percent <float>`: Percentage of top internet results to keep.
    -   `--research-filter-percent <float>`: Percentage of top paper results to keep.
-   `--run-fetching`: Enable the content extraction stage for filtered results.
-   `--pages-to-visit <int>`: Number of pages for AI query generator to explore (default: 5).

### Running Specific Stages

-   **Generate queries (if not done automatically with a topic):**
    The query generation is part of the `query_agent.py` and is usually called by `main.py` when a topic is provided.

-   **Run only Quality Assessment (on existing unassessed results):**
    ```bash
    python src/main.py --run-assessment [--assessment-batch-size 10]
    ```

-   **Run only Result Filtering (on existing assessed results):**
    ```bash
    python src/main.py --run-filtering --internet-filter-percent 10 --research-filter-percent 10
    ```
-   **Run only Content Fetching (on previously filtered results):**
    This is typically done by running the main workflow with `--run-fetching` after results have been filtered. If you need to re-run fetching on an existing database state where results are already marked as top candidates:
    ```bash
    python src/main.py --run-fetching --topic "Dummy Topic To Satisfy Argparser" --max-queries 0
    ```
    (The dummy topic and max-queries 0 ensure no new searching occurs, and it proceeds to fetching if applicable.)
    Alternatively, ensure your database has filtered results and run:
    ```bash
    python src/main_part2.py --db-path data/research_db.db
    ```
    *(Adjust `main_part2.py` if it requires more arguments or context from `main.py`)*


## Database

The system uses SQLite. The default database file is `data/research_db.db`. Key tables include:
-   `search_queries`: Stores topics and generated search queries.
-   `web_resources`: Metadata of discovered web resources (URLs, titles, snippets).
-   `quality_assessments`: AI-generated scores for each resource.
-   `content_cache`: Extracted textual content from fetched pages/PDFs.

## Logging

-   Logs are written to the console and to timestamped files in the `logs/` directory (e.g., `logs/main_workflow_YYYYMMDD_HHMMSS.log`).
-   Log level can be configured via the `LOG_LEVEL` environment variable.

## Contributing

(Details on how to contribute, if applicable - e.g., coding standards, pull request process)

## License

(Specify the license for the project, e.g., MIT, Apache 2.0)