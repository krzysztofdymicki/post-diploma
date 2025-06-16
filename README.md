# Automated Academic Research Workflow System

## Overview

This project is an automated system designed to streamline the academic research process, specifically for gathering and assessing literature and scientific sources. It assists researchers by implementing a five-stage workflow:

1.  **AI-Powered Query Generation:** An AI agent, using DuckDuckGo for initial research, expands a general research topic into a set of detailed and diverse search queries optimized for comprehensive coverage.
2.  **Multi-Channel Search:** The system executes these queries across general internet searches (via DuckDuckGo API) and academic databases (via Semantic Scholar API) to find relevant articles, reports, and scientific publications.
3.  **AI-Driven Quality Assessment:** Each found resource is evaluated by an AI model (gemini-2.5-flash-preview-05-20) based on predefined criteria: relevance, credibility (for internet sources), solidity, and overall usefulness. Assessments are justified and stored.
4.  **Result Filtering:** Based on user-defined percentage thresholds, the system filters the assessed resources, retaining only the highest-quality items from both internet and academic searches to reduce information noise.
5.  **Conditional Content Extraction and Persistence:** For selected high-quality resources (primarily internet sources, if technically feasible and access is not restricted), a browsing agent attempts to extract the main textual content from HTML pages or directly accessible PDFs. All gathered data, including queries, metadata, assessments, and extracted content, is stored in an SQLite database.

The system is built with a modular Python architecture and aims to provide a systematic, repeatable, and efficient method for literature review and source material collection.

## Features

-   **AI-Powered Query Generation:** An AI agent conducts preliminary research on a given topic (using DuckDuckGo) to generate a comprehensive set of specific search queries.
-   **Multi-Source Information Retrieval:** Searches the general web (DuckDuckGo API via `duckduckgo_search` library) and academic databases (Semantic Scholar API).
-   **AI-Driven Quality Assessment:** Utilizes the `gemini-2.5-flash-preview-05-20` model to evaluate resources based on relevance, credibility, solidity, and overall usefulness, providing weighted scores and justifications.
-   **Configurable Filtering:** Allows users to define percentage-based thresholds to select the top-tier results from different source types.
-   **Conditional Content Extraction:** Attempts to fetch and parse text from selected HTML pages and PDF documents, focusing on the main content.
-   **Database Persistence:** Stores all generated queries, resource metadata, AI assessments, and extracted content in a structured SQLite database for integrity and reproducibility.
-   **Deduplication:** (Assumed, as good practice, though not explicitly in the new text - can be kept if system supports it) Avoids redundant processing of identical queries and resources.
-   **Comprehensive Logging:** Tracks all operations, successes, and errors.
-   **Flexible CLI:** Allows running the full workflow or individual stages with various parameters.
-   **Reproducibility:** Saves detailed workflow results, configurations, and generated queries.

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
├── requirements.txt        # Python package dependencies
├── .gitignore              # Specifies intentionally untracked files
├── .env.example            # Template for environment variables
├── .env                    # Local environment variables (should be in .gitignore)
├── README.md               # This file
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

This command will execute the five-stage process: generate queries (if a topic is provided and no query file), search, assess, filter, and conditionally fetch content.

```bash
python src/main.py --topic "Your Research Topic" --run-fetching [--clear-db] [other_options]
```

**Example:**

```bash
python src/main.py ^
  --topic "sentiment analysis application/use-cases in the world, review" ^
  --max-queries 10 ^
  --internet-filter-percent 20 ^
  --research-filter-percent 30 ^
  --run-fetching ^
  --clear-db
```
*(Note: `^` is the line continuation character for Windows Command Prompt. Use `\` for PowerShell or bash.)*

### Key CLI Options

-   `--topic <str>`: Initial research topic for AI query generation.
-   `--queries-file <Path>`: Use an existing JSON file of search queries (skips Stage 1).
-   `--db-path <str>`: Path to the SQLite database (default: `data/research_db.db`).
-   `--clear-db`: Clear the database before running. **Use with caution.**
-   `--max-queries <int>`: Limit the number of queries to process.
-   `--internet-only`: Use only internet search.
-   `--papers-only`: Use only academic paper search.
-   `--run-assessment`: Explicitly run Stage 3: Quality Assessment (on existing unassessed results).
    -   `--assessment-batch-size <int>`: Batch size for assessment.
-   `--run-filtering`: Explicitly run Stage 4: Result Filtering (on existing assessed results).
    -   `--internet-filter-percent <float>`: Percentage of top internet results to keep (e.g., 20 for 20%).
    -   `--research-filter-percent <float>`: Percentage of top paper results to keep (e.g., 30 for 30%).
-   `--run-fetching`: Enable Stage 5: Content Extraction for filtered results.
-   `--pages-to-visit <int>`: Number of pages for AI query generator (Stage 1) to explore for thematic understanding (default: 5).

### Running Specific Stages

-   **Stage 1: Generate queries:**
    This is typically initiated by `src/main.py` when a `--topic` is provided and no `--queries-file` is specified.

-   **Stage 3: Run only Quality Assessment (on existing unassessed results):**
    ```bash
    python src/main.py --run-assessment [--assessment-batch-size 10]
    ```

-   **Stage 4: Run only Result Filtering (on existing assessed results):**
    ```bash
    python src/main.py --run-filtering --internet-filter-percent 20 --research-filter-percent 30
    ```
-   **Stage 5: Run only Content Fetching (on previously filtered results):**
    This is typically done by running the main workflow with `--run-fetching` after results have been filtered. To run it standalone on an existing database with filtered results:
    ```bash
    python src/main.py --run-fetching --topic "Dummy Topic To Satisfy Argparser" --max-queries 0
    ```
    (The dummy topic and max-queries 0 prevent new searching, proceeding to fetching if applicable.)
    Alternatively, ensure your database has filtered results and run:
    ```bash
    python src/main_part2.py --db-path data/research_db.db
    ```
    *(Adjust `main_part2.py` if it requires more arguments or context from `main.py`)*


## Database

The system uses SQLite. The default database file is `data/research_db.db`. Key tables include:
-   `search_queries`: Stores initial topics and AI-generated search queries.
-   `web_resources`: Metadata of discovered web resources (URLs, titles, abstracts/snippets) from DuckDuckGo and Semantic Scholar.
-   `quality_assessments`: AI-generated scores and justifications for each resource, based on relevance, credibility, solidity, and usefulness.
-   `content_cache`: Conditionally extracted textual content from fetched pages/PDFs.

## Logging

-   Logs are written to the console and to timestamped files in the `logs/` directory (e.g., `logs/main_workflow_YYYYMMDD_HHMMSS.log`).
-   Log level can be configured via the `LOG_LEVEL` environment variable.

## Contributing

(Details on how to contribute, if applicable - e.g., coding standards, pull request process)

## License

(Specify the license for the project, e.g., MIT, Apache 2.0)
