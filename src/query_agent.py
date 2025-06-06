"""
Query Agent - Universal Research Query Generation Agent

This agent uses smolagents and Google Gemini 2.5 Flash to:
1. Interactively ask users about their research topic and source preferences
2. Explore the topic online to understand its full scope
3. Generate 15-20 optimized search queries covering the complete research landscape

The agent is designed to be universal (not limited to any specific domain).
"""

import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from smolagents import CodeAgent, OpenAIServerModel, WebSearchTool

# Load environment variables from .env file
load_dotenv()

# Get API key from environment
api_key = os.getenv('GEMINI_API_KEY')
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# Initialize tools for the agent
from smolagents import VisitWebpageTool
web_search_tool = WebSearchTool()
visit_webpage_tool = VisitWebpageTool()

# Extended system prompt that will be APPENDED to the default smolagents prompt
EXTENDED_SYSTEM_PROMPT = """
You are a research assistant specialized in generating comprehensive search queries for academic research.
"""

# Initialize the agent first, then modify system prompt by appending our extension
agent = CodeAgent(
    tools=[web_search_tool, visit_webpage_tool], 
    model=OpenAIServerModel(
        model_id="gemini-2.5-flash-preview-05-20",
        api_key=api_key,
        api_base="https://generativelanguage.googleapis.com/v1beta/openai/"
    ), 
    add_base_tools=True
)

# Combine default system prompt with our specialized extension
combined_system_prompt = agent.system_prompt + EXTENDED_SYSTEM_PROMPT
agent.system_prompt = combined_system_prompt

def save_agent_logs_to_file(filename: str = None, detailed: bool = False):
    """
    Save agent logs to a text file using new smolagents API.
    
    Args:
        filename: Optional filename. If None, generates timestamp-based filename.
        detailed: If True, saves all log details. If False, saves compact summary.
    """
    try:
        # Use new API: agent.memory.steps instead of agent.logs
        if not hasattr(agent, 'memory') or not hasattr(agent.memory, 'steps') or not agent.memory.steps:
            print("📝 No logs to save.")
            return
        
        # Create logs directory if it doesn't exist
        import os
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        
        # Generate filename if not provided
        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(logs_dir, f"query_agent_logs_{timestamp}.txt")
        else:
            # If custom filename provided, ensure it's in logs directory
            filename = os.path.join(logs_dir, filename)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("="*60 + "\n")
            f.write("📋 QUERY AGENT EXECUTION LOGS\n")
            f.write("="*60 + "\n")
            
            for i, step in enumerate(agent.memory.steps):
                f.write(f"\n🔍 Step {i+1} ({type(step).__name__}):\n")
                f.write("-" * 40 + "\n")
                
                # Convert step to string representation
                step_info = str(step)
                if detailed:
                    f.write(f"{step_info}\n")
                else:
                    # Save compact version
                    if len(step_info) > 200:
                        f.write(f"{step_info[:200]}...\n")
                    else:
                        f.write(f"{step_info}\n")
            
            f.write("\n" + "="*60 + "\n")
            f.write(f"📊 Total steps: {len(agent.memory.steps)}\n")
        
        print(f"💾 Logs saved to: {filename}")
        return filename
        
    except Exception as e:
        print(f"❌ Error saving logs: {e}")
        return None

def clear_agent_logs():
    """Clear agent logs for a fresh start."""
    try:
        if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps'):
            agent.memory.steps = []
            print("🗑️ Agent logs cleared.")
        else:
            print("📝 No logs to clear.")
    except Exception as e:
        print(f"❌ Error clearing logs: {e}")

def collect_user_requirements():
    """
    Collect research requirements from user via command line.
    
    Returns:
        dict: User requirements including topic, pages to visit, etc.
    """
    print("🔍 Research Query Generation Setup")
    print("=" * 50)
    
    # Get research topic
    while True:
        topic = input("📝 Please enter your research topic: ").strip()
        if topic:
            break
        print("❌ Please provide a research topic.")
    
    # Get number of pages to visit
    while True:
        try:
            pages_input = input("🌐 How many web pages should the agent visit for exploration? (1-20, default: 5): ").strip()
            if not pages_input:
                pages_to_visit = 5
                break
            pages_to_visit = int(pages_input)
            if 1 <= pages_to_visit <= 20:
                break
            else:
                print("❌ Please enter a number between 1 and 20.")
        except ValueError:
            print("❌ Please enter a valid number.")
    
    # Get additional focus areas (optional)
    focus_areas = input("🎯 Any specific focus areas or constraints? (optional, press Enter to skip): ").strip()
    
    # Get source preferences (optional)
    source_prefs = input("📚 Preferred information sources? (e.g., academic papers, industry articles, news) (optional): ").strip()
    
    return {
        'topic': topic,
        'pages_to_visit': pages_to_visit,
        'focus_areas': focus_areas if focus_areas else None,
        'source_preferences': source_prefs if source_prefs else None
    }

def generate_research_prompt(requirements: dict) -> str:
    """
    Generate a specific research prompt based on user requirements.
    
    Args:
        requirements: Dictionary with user requirements
        
    Returns:
        str: Formatted prompt for the agent
    """
    prompt_parts = [
        f"=== RESEARCH QUERY GENERATION TASK ===",
        f"",
        f"Research Topic: {requirements['topic']}",
        f"Pages to visit: {requirements['pages_to_visit']}",
    ]
    
    if requirements['focus_areas']:
        prompt_parts.append(f"Specific focus areas: {requirements['focus_areas']}")
    
    if requirements['source_preferences']:
        prompt_parts.append(f"Preferred sources: {requirements['source_preferences']}")
    
    prompt_parts.extend([
        "",
        "=== YOUR MISSION ===",
        "Your goal is to gain a comprehensive perspective on this research topic by exploring it online,",
        "then generate detailed search queries that will be used for actual research and content analysis for academic work.",
        "",
        "=== YOUR WORKFLOW ===",
        "",
        "**STEP 1: DEEP TOPIC EXPLORATION**",
        "- Use the `web_search` tool to investigate the research topic from multiple angles",
        "- Perform diverse searches to understand the complete landscape of the topic",
        f"- MANDATORY: Use the `visit_webpage` tool to actually READ the content of the most promising pages you find",
        f"- Visit EXACTLY {requirements['pages_to_visit']} relevant pages to gather detailed information",
        "- Focus on understanding what is truly important and relevant in this field",
        "",        "**STEP 2: COMPREHENSIVE SEARCH QUERY GENERATION**",
        "- Based on your deep exploration and page visits, generate EXACTLY 15-20 optimized search queries",
        "- These queries must be the BEST possible ones, summarizing and synthesizing ALL the context gathered from different pages",
        "- They must optimally reflect and cover the user's topic based on your comprehensive research",
        "- These must be actual search queries for use in search engines, databases, and academic platforms",
        "- Format: Clear, concise search terms and phrases (2-8 words maximum)",
        "- Include Boolean operators (AND, OR, NOT) where appropriate",
        "- Use quotation marks for exact phrases when needed",
        "",
        "**OUTPUT FORMAT:**",
        "Provide your response as valid JSON in this exact format:",
        '{"queries": ["query 1", "query 2", "query 3", ..., "query 20"]}',
        "",
        "IMPORTANT: Return ONLY the JSON object, nothing else. No explanations, no additional text.",
        "",
        "START NOW!"
    ])
    
    return "\n".join(prompt_parts)

def parse_queries_from_response(response) -> List[str]:
    """
    Parse search queries from agent's response.
    
    Args:
        response: Agent's response (can be dict or string)
        
    Returns:
        List of search queries
    """
    try:
        # If response is already a dict (as returned by smolagents)
        if isinstance(response, dict):
            return response.get('queries', [])
        
        # If response is a string, try to parse JSON
        if isinstance(response, str):
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                return data.get('queries', [])
        
        print("❌ No valid data found in response")
        return []
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON: {e}")
        return []
    except Exception as e:
        print(f"❌ Error extracting queries: {e}")
        return []

def run_query_generation():
    """
    Run the complete query generation process.
    """
    print("� Universal Research Query Generation Agent")
    print("=" * 60)
    print("This agent will help you generate comprehensive search queries for academic research.")
    print("It will explore your topic online and create 15-20 optimized search queries.")
    print("=" * 60)
    
    try:
        # Collect requirements from user
        requirements = collect_user_requirements()
        
        # Generate specific prompt
        research_prompt = generate_research_prompt(requirements)
        
        print(f"\n🔍 Starting research exploration for: {requirements['topic']}")
        print(f"📊 Will visit {requirements['pages_to_visit']} web pages for comprehensive analysis")
        print("\n⏳ Agent is working... (this may take a few minutes)")
          # Run the agent with the generated prompt
        response = agent.run(research_prompt)
        
        # Parse queries from JSON response
        queries = parse_queries_from_response(response)
        
        print("\n" + "="*60)
        print("🎯 GENERATED SEARCH QUERIES")
        print("="*60)
        
        if queries:
            print(f"✅ Successfully generated {len(queries)} search queries:\n")
            for i, query in enumerate(queries, 1):
                print(f"{i:2d}. {query}")
              # Also save queries to a JSON file for easy integration
            from datetime import datetime
            import os
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create outputs directory if it doesn't exist
            outputs_dir = "outputs"
            os.makedirs(outputs_dir, exist_ok=True)
            
            queries_filename = os.path.join(outputs_dir, f"query_agent_search_queries_{timestamp}.json")
            
            try:
                with open(queries_filename, 'w', encoding='utf-8') as f:
                    json.dump({"topic": requirements['topic'], "queries": queries}, f, indent=2, ensure_ascii=False)
                print(f"\n💾 Queries saved to: {queries_filename}")
            except Exception as e:
                print(f"❌ Error saving queries to file: {e}")
        else:
            print("❌ No queries were successfully extracted from the response.")
            print("\n📄 Raw agent response:")
            print("-" * 40)
            print(response)
        
        return True
        
    except KeyboardInterrupt:
        print("\n� Process interrupted. Goodbye!")
        return False
    except Exception as e:
        print(f"❌ Error during query generation: {e}")
        return False

if __name__ == "__main__":
    try:
        # Run the query generation process
        success = run_query_generation()
        
    finally:
        # Always save logs when exiting
        try:
            if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps') and agent.memory.steps:
                print("\n💾 Saving session logs...")
                filename = save_agent_logs_to_file()
                if filename:
                    print(f"📁 Session logs saved to: {filename}")
            else:
                print("📝 No logs to save from this session.")
        except Exception as e:
            print(f"❌ Error during log saving: {e}")
