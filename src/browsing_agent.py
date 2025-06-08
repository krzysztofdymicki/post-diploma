from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent
from dotenv import load_dotenv
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Read GOOGLE_API_KEY into env
load_dotenv()

# Initialize the model
llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')

class ContentExtractionAgent:
    """Agent for extracting main content from web pages using browser-use."""
    
    def __init__(self, llm):
        self.llm = llm
        logger.info("ContentExtractionAgent initialized")
    
    async def extract_content_from_url(self, url: str) -> dict:
        """
        Extract main content from a single URL.
        
        Args:
            url: The URL to extract content from
            
        Returns:
            dict: Contains extracted content, title, and metadata
        """
        logger.info(f"Starting content extraction for URL: {url}")
        
        # Define the task for content extraction
        task = f"""
        Please extract the main content from the webpage at {url}. 
        I need you to:
        1. Navigate to the URL
        2. Extract the main text content (articles, main body text, excluding navigation, ads, footers)
        3. Extract the page title
        4. Provide a brief summary of what the page is about
        5. Return the extracted information in a structured format
        
        Focus on the core content that would be useful for research purposes.
        """
        
        # Initial actions to navigate to the URL
        initial_actions = [
            {'open_tab': {'url': url}},
            {'wait': {'seconds': 3}},  # Wait for page to load
        ]
        
        try:
            # Create and run the agent
            agent = Agent(
                task=task,
                initial_actions=initial_actions,
                llm=self.llm,
            )
            
            result = await agent.run(max_steps=30)
            
            logger.info(f"Content extraction completed for {url}")
            logger.info(f"Result type: {type(result)}")
            logger.info(f"Result: {str(result)[:500]}...")  # First 500 chars
            
            return {
                'url': url,
                'status': 'success',
                'extracted_content': str(result),
                'agent_result': result
            }
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return {
                'url': url,
                'status': 'error',
                'error_message': str(e),
                'extracted_content': None
            }
    
    async def extract_content_from_multiple_urls(self, urls: list) -> list:
        """
        Extract content from multiple URLs sequentially.
        
        Args:
            urls: List of URLs to process
            
        Returns:
            list: List of extraction results
        """
        logger.info(f"Starting batch content extraction for {len(urls)} URLs")
        results = []
        
        for i, url in enumerate(urls, 1):
            logger.info(f"Processing URL {i}/{len(urls)}: {url}")
            result = await self.extract_content_from_url(url)
            results.append(result)
            
            # Small delay between requests to be respectful
            if i < len(urls):
                await asyncio.sleep(2)
        
        logger.info(f"Batch extraction completed. {len(results)} results.")
        return results


# Test function
async def test_single_url():
    """Test content extraction with a single URL."""
    logger.info("=== TESTING SINGLE URL CONTENT EXTRACTION ===")
    
    # Test with Wikipedia page (reliable structure)
    test_url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
    
    agent = ContentExtractionAgent(llm)
    result = await agent.extract_content_from_url(test_url)
    
    print("\n" + "="*80)
    print("CONTENT EXTRACTION RESULT")
    print("="*80)
    print(f"URL: {result['url']}")
    print(f"Status: {result['status']}")
    
    if result['status'] == 'success':
        print(f"Extracted content length: {len(result['extracted_content'])} characters")
        print("\nFirst 1000 characters of extracted content:")
        print("-" * 50)
        print(result['extracted_content'][:1000])
        print("-" * 50)
    else:
        print(f"Error: {result.get('error_message', 'Unknown error')}")
    
    return result


async def test_multiple_urls():
    """Test content extraction with multiple URLs."""
    logger.info("=== TESTING MULTIPLE URLs CONTENT EXTRACTION ===")
    
    # Test URLs - mix of different types
    test_urls = [
        "https://en.wikipedia.org/wiki/Machine_learning",
        "https://en.wikipedia.org/wiki/Natural_language_processing",
        # Add more URLs as needed
    ]
    
    agent = ContentExtractionAgent(llm)
    results = await agent.extract_content_from_multiple_urls(test_urls)
    
    print("\n" + "="*80)
    print("BATCH CONTENT EXTRACTION RESULTS")
    print("="*80)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. URL: {result['url']}")
        print(f"   Status: {result['status']}")
        if result['status'] == 'success':
            content_length = len(result['extracted_content'])
            print(f"   Content length: {content_length} characters")
            print(f"   Preview: {result['extracted_content'][:200]}...")
        else:
            print(f"   Error: {result.get('error_message', 'Unknown error')}")
    
    return results


# Main function for testing
async def main():
    """Main function to run tests."""
    print("🤖 CONTENT EXTRACTION AGENT TEST")
    print("="*80)
    
    try:
        # Test 1: Single URL
        await test_single_url()
        
        # Uncomment to test multiple URLs
        # print("\n\n")
        # await test_multiple_urls()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())