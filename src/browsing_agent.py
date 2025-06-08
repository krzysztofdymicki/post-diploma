import os
import logging
from pathlib import Path
import time
from time import sleep # Added this import
import io # For BytesIO
from urllib.parse import urljoin

import helium
from PIL import Image # For screenshots
from selenium import webdriver # For ChromeOptions, ActionChains
from selenium.webdriver.common.keys import Keys # For Keys.ESCAPE
import requests
from bs4 import BeautifulSoup

from smolagents import CodeAgent, tool
from smolagents.agents import ActionStep # For type hinting in callback

# Configure logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s')


class BrowsingAgent:  # No longer inherits from smolagents.Agent directly
    def __init__(self, database, output_dir="outputs/retrieved_content", gemini_api_key=None, headless_helium=True):
        if not gemini_api_key:
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if not gemini_api_key:
                raise ValueError("GEMINI_API_KEY must be provided or set as an environment variable.")

        self.database = database
        self.output_dir = Path(output_dir)
        self.pdf_output_dir = self.output_dir / "pdfs"
        self.html_output_dir = self.output_dir / "html" # Optional

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_output_dir.mkdir(parents=True, exist_ok=True)
        self.html_output_dir.mkdir(parents=True, exist_ok=True) # Optional

        # Configure Chrome options as in the example
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--force-device-scale-factor=1")
        chrome_options.add_argument("--window-size=1000,1350") # Example size
        chrome_options.add_argument("--disable-pdf-viewer") # To prevent Chrome from opening PDFs internally
        chrome_options.add_argument("--window-position=0,0")
        # Add any other options you find necessary, e.g., user-agent
        # chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")


        try:
            logger.info(f"Starting Helium with headless={headless_helium}...")
            # helium.start_chrome has its own driver management. We get the driver instance.
            self.driver = helium.start_chrome(headless=headless_helium, options=chrome_options)
            logger.info("Helium started successfully with Chrome.")
        except Exception as e:
            logger.error(f"Failed to start Helium: {e}. Ensure ChromeDriver is in PATH or check permissions.")
            raise

        # Initialize CodeAgent
        # CodeAgent inherits from Agent, so it should accept model_config
        self.code_agent = CodeAgent(
            name="WebInteractingCodeAgent",
            role="An AI agent that writes and executes Python code using Helium and other libraries to navigate websites, extract information, and download files based on detailed instructions.",
            system_prompt="You are a meticulous AI assistant that translates natural language instructions into Python code for web automation. Execute the code and use provided tools to report results or errors. Follow instructions precisely.",
            tools=[self._save_html_content_tool, self._save_pdf_tool, self._report_error_tool, self.close_popups_tool],
            model_config={'api_key': gemini_api_key, 'model_name': 'gemini-1.5-flash-preview-05-20'}, # User-specified model
            additional_authorized_imports=[
                "helium", "requests", "bs4", "urllib.parse",
                "selenium.webdriver.common.by", "selenium.webdriver.common.keys", # For By and Keys if agent needs them
                "os", "json", "time", "io" # General useful modules
            ],
            step_callbacks=[self._save_screenshot_callback], # Pass the method directly
            max_steps=50, # Increased for potentially complex sequence of finding PDF and downloading
            verbosity_level=2,
        )

        # Make libraries available in the agent's Python execution environment
        # These are executed once in the agent's state when it's initialized.
        self.code_agent.python_executor("from helium import *", self.code_agent.state)
        self.code_agent.python_executor("import requests", self.code_agent.state)
        self.code_agent.python_executor("from bs4 import BeautifulSoup", self.code_agent.state)
        self.code_agent.python_executor("from urllib.parse import urljoin", self.code_agent.state)
        self.code_agent.python_executor("import time", self.code_agent.state)
        self.code_agent.python_executor("import os", self.code_agent.state)
        # For popup tool, if it needs Keys directly in agent-generated code (though the tool handles it)
        self.code_agent.python_executor("from selenium.webdriver.common.keys import Keys", self.code_agent.state)


    def _save_screenshot_callback(self, memory_step: ActionStep, agent: CodeAgent) -> None:
        """Saves a screenshot after each action step of the CodeAgent."""
        try:
            sleep(1.0)  # Let JavaScript animations happen
            if self.driver is not None:
                # Remove previous screenshots for lean processing (from example)
                # current_step = memory_step.step_number
                # for prev_step in agent.memory.steps:
                #     if isinstance(prev_step, ActionStep) and prev_step.step_number <= current_step - 2:
                #         prev_step.observations_images = None
                
                png_bytes = self.driver.get_screenshot_as_png()
                image = Image.open(io.BytesIO(png_bytes))
                # logger.debug(f"Captured a browser screenshot: {image.size} pixels for step {memory_step.step_number}")
                if memory_step: # Ensure memory_step is not None
                     memory_step.observations_images = [image.copy()]

                # Update observations with current URL (from example)
                url_info = f"Current URL: {self.driver.current_url}"
                if memory_step:
                    if memory_step.observations is None:
                        memory_step.observations = url_info
                    else:
                        memory_step.observations += "\n" + url_info
            else:
                logger.warning("Driver not available for screenshot.")
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}", exc_info=True)

    @tool
    def _save_html_content_tool(self, query_result_id: int, url: str, html_content: str):
        """
        TOOL: Call this to save the fetched HTML content for a given URL and its query_result_id.
        Args:
            query_result_id: The ID of the query result in the database.
            url: The URL from which the HTML was fetched.
            html_content: The HTML content as a string.
        """
        self.database.update_or_insert_fetched_content(query_result_id, "html", html_content, None)
        msg = f"Successfully saved HTML content for QueryResultID {query_result_id} ({url})."
        logger.info(msg)
        return msg

    @tool
    def _save_pdf_tool(self, query_result_id: int, url: str, pdf_filepath: str, original_pdf_url: str):
        """
        TOOL: Call this to record the successful download of a PDF and its local filepath.
        Args:
            query_result_id: The ID of the query result in the database.
            url: The original page URL where the PDF link was found (this is the page URL, not the PDF direct URL).
            pdf_filepath: The absolute local path where the PDF was saved.
            original_pdf_url: The direct URL of the PDF that was downloaded.
        """
        self.database.update_or_insert_fetched_content(query_result_id, "pdf_path", pdf_filepath, None)
        msg = f"Successfully recorded PDF download for QueryResultID {query_result_id} (page URL: {url}), PDF from {original_pdf_url} saved to {pdf_filepath}."
        logger.info(msg)
        return msg

    @tool
    def _report_error_tool(self, query_result_id: int, url: str, error_message: str, content_type_tried: str = "unknown"):
        """
        TOOL: Call this to report an error encountered while trying to fetch content for a URL.
        Args:
            query_result_id: The ID of the query result in the database.
            url: The URL for which processing failed.
            error_message: A description of the error.
            content_type_tried: The type of content that was being attempted (e.g., 'html', 'pdf').
        """
        db_error_message = f"CodeAgent error ({content_type_tried}): {error_message[:1000]}" # Increased length
        self.database.update_or_insert_fetched_content(query_result_id, content_type_tried, None, db_error_message)
        msg = f"Error reported for QueryResultID {query_result_id} ({url}): {error_message}"
        logger.error(msg) # Log as error
        return msg

    @tool
    def close_popups_tool(self) -> str:
        """
        TOOL: Closes any visible modal or pop-up on the page by sending the ESCAPE key.
        Use this to dismiss pop-up windows! This may not work on cookie consent banners.
        """
        try:
            if self.driver:
                webdriver.ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                msg = "Sent ESCAPE key to close popups."
                logger.info(msg)
                return msg
            return "Driver not available to close popups."
        except Exception as e:
            msg = f"Error trying to send ESCAPE key: {e}"
            logger.warning(msg)
            return msg

    def _get_agent_instructions(self) -> str:
        """Provides general instructions on how to use Helium and custom tools."""
        return '''
You are equipped with Python execution capabilities.
The following libraries have ALREADY BEEN IMPORTED for you: `helium` (as `*`), `requests`, `bs4.BeautifulSoup`, `urllib.parse.urljoin`, `time`, `os`.
The Helium browser driver is managed. You can use Helium commands directly.

Key Helium Commands:
- `go_to('https://example.com')`
- `click("Clickable Text")` or `click(Link("Link Text"))`
- `get_driver().page_source` to get current page HTML.
- `S("css_selector").element.get_attribute('href')` to get attributes.
- `scroll_down(num_pixels=1000)`, `scroll_up(num_pixels=1000)`
- `Text('some text').exists()`
- `write("text", into="input field name or S object")`
- `press(ENTER)`

Finding PDF links (example using BeautifulSoup, which is available):
```python
# html_content = get_driver().page_source
# soup = BeautifulSoup(html_content, 'html.parser')
# base_url = get_driver().current_url
# pdf_links = []
# for a_tag in soup.find_all('a', href=True):
#     href = a_tag['href']
#     link_text = a_tag.get_text().lower()
#     abs_href = urljoin(base_url, href)
#     if abs_href.lower().endswith('.pdf'):
#         pdf_links.append(abs_href)
#     elif 'pdf' in link_text or 'full text' in link_text:
#         pdf_links.append(abs_href)
# if pdf_links:
#   found_pdf_url = pdf_links[0] # Choose the best one
```

Downloading files with `requests`:
```python
# import requests # (already imported for you)
# response = requests.get(pdf_url_to_download, stream=True, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
# response.raise_for_status() # Raises an exception for bad status codes
# with open(local_filepath_to_save, 'wb') as f:
#   for chunk in response.iter_content(chunk_size=8192):
#     f.write(chunk)
```

Using Your Tools (IMPORTANT: Call these as Python functions when appropriate):
- `_save_html_content_tool(query_result_id: int, url: str, html_content: str)`: Call after successfully fetching HTML.
- `_save_pdf_tool(query_result_id: int, url: str, pdf_filepath: str, original_pdf_url: str)`: Call *after* successfully downloading a PDF to a local file. `pdf_filepath` is the local path. `url` is the original page URL. `original_pdf_url` is the direct PDF link.
- `_report_error_tool(query_result_id: int, url: str, error_message: str, content_type_tried: str)`: Call for unrecoverable errors. `content_type_tried` is 'html' or 'pdf'.
- `close_popups_tool()`: Call if you encounter obstructive popups.

Follow the specific TASK instructions for each item carefully.
Do not try to login. Be methodical.
'''

    def _create_task_prompt_for_item(self, url: str, source_type: str, query_result_id: int, title: str) -> str:
        """Creates a specific task prompt for the CodeAgent for a single item."""
        safe_title = "".join(c if c.isalnum() else '_' for c in title[:50]) # Shorter, safer title for filenames
        # Agent needs to know the absolute path for saving PDFs, constructed with its own `os.path.join`
        # So we provide the directory.
        pdf_output_directory = str(self.pdf_output_dir.resolve())

        task_description = f"""
TASK: Process URL: {url} (QueryResultID: {query_result_id}, Original Title Hint: '{title}')

Your objective is to fetch content from this URL and report back using the provided tools.

1.  Navigate to the URL: `go_to('{url}')`. Wait for the page to load (e.g., `time.sleep(5)` or wait for an element).
2.  Attempt to close any initial popups using `close_popups_tool()`.
3.  Get the full HTML content: `html_page_content = get_driver().page_source`.

IF `source_type` is 'paper' (this item's source_type is: '{source_type}'):
    a.  Analyze `html_page_content` to find a direct link to a PDF document.
        Use techniques like searching for `<a>` tags with `href` ending in '.pdf', or link text like 'Download PDF', 'Full Text PDF'.
        Make sure the found PDF URL is absolute (use `urljoin(get_driver().current_url, relative_link)` if needed).
    b.  If a promising PDF link (`found_pdf_url`) is identified:
        i.  Log the found PDF URL for debugging (e.g. `print(f"Found PDF link: {{found_pdf_url}}")`).
        ii. Construct the local PDF filename: `pdf_filename = "paper_{query_result_id}_{safe_title}.pdf"`
            (using `query_result_id={query_result_id}` and `safe_title='{safe_title}'`).
        iii.Construct the full local save path: `local_pdf_filepath = os.path.join("{pdf_output_directory}", pdf_filename)`.
            (Ensure `{pdf_output_directory}` is treated as a string representing the directory).
        iv. Download the PDF from `found_pdf_url` to `local_pdf_filepath` using the `requests` library (see general instructions for example).
            Handle potential errors during download (e.g., `try-except` block).
        v.  If download is successful:
            Call `_save_pdf_tool(query_result_id={query_result_id}, url='{url}', pdf_filepath=local_pdf_filepath, original_pdf_url=found_pdf_url)`.
            Your task for this item is then complete.
        vi. If PDF download fails (e.g., network error, bad status code, content is not PDF):
            Log the error (e.g. `print("PDF download failed.")`). Fall through to step 4 (saving HTML of the page).
    c.  If no suitable PDF link is found after careful searching:
        Log this (e.g. `print("No suitable PDF link found.")`). Proceed to step 4.

ELSE (source_type is not 'paper'):
    Proceed directly to step 4.

4.  (Fallback or primary for non-paper) Save HTML content:
    Call `_save_html_content_tool(query_result_id={query_result_id}, url='{url}', html_content=html_page_content)`.

ERROR HANDLING:
If any unrecoverable error occurs at any stage that prevents you from completing one of the primary save operations (`_save_pdf_tool` or `_save_html_content_tool`), you MUST call:
`_report_error_tool(query_result_id={query_result_id}, url='{url}', error_message='<Your detailed error description>', content_type_tried='<html_or_pdf_being_attempted>')`.

Think step-by-step. Be careful with variable names and ensure you pass correct arguments to tools.
"""
        return task_description

    def process_filtered_results(self, filtered_results: dict):
        all_items = []
        # The filtering module now returns 'paper' and 'internet' keys directly.
        if 'paper' in filtered_results:
            all_items.extend(filtered_results['paper'])
        if 'internet' in filtered_results:
            all_items.extend(filtered_results['internet'])

        logger.info(f"BrowsingAgent (CodeAgent mode) will process {len(all_items)} items.")
        
        # Get general instructions once
        agent_general_instructions = self._get_agent_instructions()

        for i, item in enumerate(all_items):
            url = item.get('url')
            # Determine source_type for the task prompt. The filtering module should provide this.
            # Assuming 'item' from filtered_results has a 'source_type' field.
            # If 'research_papers' was mapped to 'paper' in main_part2.py, this should be fine.
            source_type = item.get('source_type', 'internet') # Default to internet if not specified
            query_result_id = item.get('query_result_id') 
            title = item.get('title', f"item_{query_result_id}")

            if not url or not query_result_id:
                logger.warning(f"Skipping item with missing URL or query_result_id: {item}")
                continue

            logger.info(f"Processing item {i+1}/{len(all_items)}: QueryResultID {query_result_id}, Type: {source_type}, URL: {url}")
            
            # Check if content already fetched (optional optimization, can be added later)
            # existing_content = self.database.get_fetched_content_by_query_result(query_result_id)
            # if existing_content and existing_content.get('status') == 'success':
            #    logger.info(f"Content already successfully fetched for QueryResultID {query_result_id}. Skipping.")
            #    continue

            task_specific_prompt = self._create_task_prompt_for_item(url, source_type, query_result_id, title)
            full_prompt_for_agent = agent_general_instructions + "\n\n" + task_specific_prompt
            
            logger.debug(f"--- Full prompt for CodeAgent (QueryResultID: {query_result_id}) ---\n{full_prompt_for_agent}\n--- End Prompt ---")

            try:
                agent_final_output = self.code_agent.run(full_prompt_for_agent)
                logger.info(f"CodeAgent finished processing for QueryResultID {query_result_id}. Final output/summary: {agent_final_output}")
                # The actual saving to DB should be handled by the tools called by the agent.
            except Exception as e:
                logger.error(f"Error running CodeAgent for QueryResultID {query_result_id} ({url}): {e}", exc_info=True)
                # Fallback to report error in DB if agent itself failed catastrophically before calling a tool
                self.database.update_or_insert_fetched_content(query_result_id, "agent_execution_error", None, f"CodeAgent run() failed: {str(e)[:1000]}")
            
            time.sleep(2) # Small delay between processing items

    def close(self):
        try:
            logger.info("Attempting to kill Helium browser (via helium.kill_browser())...")
            helium.kill_browser()
            logger.info("Helium browser killed successfully.")
        except Exception as e:
            logger.warning(f"Error killing Helium browser (might be normal if already closed or if self.driver was managed differently): {e}")

