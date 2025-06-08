from dotenv import load_dotenv
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')

class ContentExtractionAgent:
    """Agent for extracting main content from web pages using browser-use."""
    def __init__(self, llm, output_dir: str = "outputs/extracted_content"):
        self.llm = llm
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.output_dir = output_dir

    async def extract_content_from_url(self, url: str, save_to_file: bool = True) -> dict:
        logger.info(f"Extracting content from: {url}")
        task = f"Navigate to {url} and extract the main text content."
        actions = [{'open_tab': {'url': url}}, {'wait': {'seconds': 3}}]
        try:
            agent = Agent(task=task, initial_actions=actions, llm=self.llm)
            result = await agent.run(max_steps=50)
            content = str(result).strip()
            logger.info(f"Success for {url}: {len(content)} chars")
            file_path = None
            if save_to_file and content:
                safe = url.replace("https://","").replace("http://","").replace("/","_")
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fname = f"{safe}_{ts}.txt"
                path = Path(self.output_dir) / fname
                with open(path,'w',encoding='utf-8') as f:
                    f.write(f"URL: {url}\nExtracted at {datetime.now()}\n\n")
                    f.write(content)
                file_path = str(path)
                logger.info(f"Saved to {file_path}")
            return {"url": url, "content": content, "file_path": file_path}
        except Exception as e:
            logger.error(f"Error for {url}: {e}")
            return {"url": url, "error": str(e)}

    # Removed get_html_content: use browser-use Agent for HTML extraction via JavaScript

    def download_pdf(self, pdf_url: str, filename: str) -> str:
        """
        Download a PDF from a URL and save it to output_dir.

        Args:
            pdf_url: URL to the PDF file
            filename: Name for the saved PDF file
        Returns:
            str: Path to saved PDF if successful, else None
        """
        import httpx
        try:
            # Follow redirects to actual PDF resource
            resp = httpx.get(pdf_url, timeout=30, follow_redirects=True)
            data = resp.content
            # Check PDF magic number
            if resp.status_code == 200 and data.startswith(b'%PDF'):
                path = Path(self.output_dir) / filename
                with open(path, 'wb') as f:
                    f.write(data)
                logger.info(f"PDF downloaded to: {path}")
                return str(path)
            logger.warning(f"PDF download failed or content not PDF (status={resp.status_code}) at: {pdf_url}")
            return None
        except Exception as e:
            logger.error(f"Exception downloading PDF from {pdf_url}: {e}")
            return None

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv)>1 else input("URL: ")
    agent = ContentExtractionAgent(llm)
    res = asyncio.run(agent.extract_content_from_url(url))
    print(res)