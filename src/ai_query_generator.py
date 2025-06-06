"""
QueryAgent - Minimal AI Agent that uses smolagents and Google Gemini 2.5 Flash.
"""

import os
from dotenv import load_dotenv
from smolagents import CodeAgent, OpenAIServerModel

# Load environment variables from .env file
load_dotenv()

# Get API key from environment
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# System prompt for the QueryAgent - following smolagents best practices
SYSTEM_PROMPT = """You are a Search Query Optimization Agent for sentiment analysis research.

Your primary responsibility is to generate and optimize search queries that maximize coverage and result quality for a bachelor's thesis on sentiment analysis, specifically for:

1. Chapter 2 - Applications of Sentiment Analysis: Real-world uses, case studies, examples across various domains
2. Chapter 3 - Sentiment Analysis Tools: Software, libraries, platforms, APIs, and techniques

Core Objectives:
- Generate diverse, high-quality search queries from user-provided topics
- Optimize existing queries for better coverage and relevance
- Ensure queries target both academic sources (research papers) and industry sources (blogs, articles)
- Maximize discovery of relevant, credible information while avoiding duplicates

Query Generation Guidelines:
- Create variations using synonyms, related terms, and different phrasings
- Include domain-specific queries (e.g., "sentiment analysis in healthcare", "social media sentiment tools")
- Balance broad exploratory queries with specific technical queries
- Consider different contexts: academic research, commercial applications, open-source tools
- Generate queries in English (primary) and consider other languages if relevant

Quality Criteria:
- Relevance to sentiment analysis applications or tools
- Potential to discover high-quality, credible sources
- Diversity to avoid redundant results
- Specificity balanced with discoverability

Always provide clear reasoning for your query suggestions and explain how they contribute to comprehensive research coverage."""

# Initialize the agent following smolagents best practices
agent = CodeAgent(
    tools=[], 
    model=OpenAIServerModel(
        model_id="gemini-2.5-flash-preview-05-20",
        api_key=api_key,
        api_base="https://generativelanguage.googleapis.com/v1beta/openai/"
    ), 
    add_base_tools=True,
    system_prompt=SYSTEM_PROMPT
)

def generate_queries_for_applications(base_topics: list) -> list:
    """
    Generate search queries focused on sentiment analysis applications.
    
    Args:
        base_topics: List of application domains (e.g., ['healthcare', 'finance', 'social media'])
    
    Returns:
        List of optimized search queries for Chapter 2 research
    """
    prompt = f"""Generate 5-8 diverse search queries for finding information about sentiment analysis APPLICATIONS in these domains: {', '.join(base_topics)}

Focus on:
- Real-world use cases and implementations
- Case studies and success stories  
- Industry applications and examples
- Business impact and outcomes

Provide queries that would work well for both academic papers and industry articles."""
    
    try:
        response = agent.run(prompt)
        return response
    except Exception as e:
        print(f"Error generating application queries: {e}")
        return []

def generate_queries_for_tools(base_topics: list) -> list:
    """
    Generate search queries focused on sentiment analysis tools and techniques.
    
    Args:
        base_topics: List of tool categories (e.g., ['python libraries', 'apis', 'platforms'])
    
    Returns:
        List of optimized search queries for Chapter 3 research
    """
    prompt = f"""Generate 5-8 diverse search queries for finding information about sentiment analysis TOOLS and TECHNIQUES in these categories: {', '.join(base_topics)}

Focus on:
- Software libraries and frameworks
- APIs and cloud services
- Analysis platforms and tools
- Algorithms and methodologies
- Comparison and evaluation studies

Provide queries that would discover both open-source and commercial solutions."""
    
    try:
        response = agent.run(prompt)
        return response
    except Exception as e:
        print(f"Error generating tool queries: {e}")
        return []

def optimize_existing_queries(queries: list, feedback: str = "") -> list:
    """
    Optimize existing queries based on results feedback.
    
    Args:
        queries: List of existing search queries
        feedback: Optional feedback about query performance
    
    Returns:
        List of optimized queries
    """
    prompt = f"""Optimize these existing search queries for better coverage and quality:

Queries: {queries}

Feedback: {feedback if feedback else 'No specific feedback provided'}

Please:
1. Identify potential gaps in coverage
2. Suggest variations that might yield different results  
3. Improve specificity where needed
4. Ensure good balance between broad and narrow queries
5. Remove or modify queries that might be too similar

Provide the optimized query list with brief explanations."""
    
    try:
        response = agent.run(prompt)
        return response
    except Exception as e:
        print(f"Error optimizing queries: {e}")
        return []

if __name__ == "__main__":
    print("=== QueryAgent - Search Query Optimization System ===")
    print("This agent generates and optimizes search queries for sentiment analysis research.")
    print("\nAvailable functions:")
    print("1. Generate queries for applications (Chapter 2)")
    print("2. Generate queries for tools (Chapter 3)")
    print("3. Optimize existing queries")
    print("4. Custom query generation")
    
    while True:
        print("\n" + "="*50)
        choice = input("\nSelect option (1-4) or 'quit': ").strip()
        
        if choice.lower() in ['quit', 'q', 'exit']:
            break
            
        try:
            if choice == '1':
                print("\n--- Generating Application Queries ---")
                domains = input("Enter application domains (comma-separated, e.g., healthcare,finance): ").strip()
                if domains:
                    topics = [d.strip() for d in domains.split(',')]
                    print(f"\nGenerating queries for domains: {topics}")
                    result = generate_queries_for_applications(topics)
                    print(f"\nGenerated queries:\n{result}")
                    
            elif choice == '2':
                print("\n--- Generating Tool Queries ---")
                categories = input("Enter tool categories (comma-separated, e.g., python libraries,apis): ").strip()
                if categories:
                    topics = [c.strip() for c in categories.split(',')]
                    print(f"\nGenerating queries for categories: {topics}")
                    result = generate_queries_for_tools(topics)
                    print(f"\nGenerated queries:\n{result}")
                    
            elif choice == '3':
                print("\n--- Optimizing Existing Queries ---")
                queries_input = input("Enter existing queries (comma-separated): ").strip()
                feedback = input("Enter feedback (optional): ").strip()
                if queries_input:
                    queries = [q.strip() for q in queries_input.split(',')]
                    print(f"\nOptimizing queries: {queries}")
                    result = optimize_existing_queries(queries, feedback)
                    print(f"\nOptimized queries:\n{result}")
                    
            elif choice == '4':
                print("\n--- Custom Query Generation ---")
                user_input = input("Enter your custom request: ").strip()
                if user_input:
                    print("\nProcessing...")
                    response = agent.run(user_input)
                    print(f"\nAgent response:\n{response}")
            else:
                print("Invalid choice. Please select 1-4 or 'quit'.")
                
        except Exception as e:
            print(f"Error: {e}")
            
    print("\n=== End QueryAgent Session ===")
