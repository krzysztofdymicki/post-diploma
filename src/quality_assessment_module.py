"""
Quality Assessment Module for Research Results

This module provides AI-powered quality assessment of search results using Google Gemini API.
It evaluates search results based on relevance, credibility, solidity, and overall usefulness 
for academic research.
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from pydantic import BaseModel, Field, ValidationError # Added ValidationError

import google.generativeai as genai
from dotenv import load_dotenv

from database import Database

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class AssessmentResponse(BaseModel):
    """Pydantic model for structured assessment response from LLM."""
    relevance_score: int = Field(description="Relevance to original query (1-5)")
    credibility_score: Optional[int] = Field(description="Source credibility score (1-5) or null for academic papers")
    solidity_score: int = Field(description="Content quality and depth (1-5)")
    overall_usefulness_score: int = Field(description="Overall usefulness for research (1-5)")
    llm_justification: str = Field(description="Brief explanation for the assessment")

# Assessment weights configuration
# Weights for calculating weighted average score (must sum to 1.0)
ASSESSMENT_WEIGHTS = {
    'relevance': 0.35,        # Najbardziej istotne - czy wynik odpowiada na zapytanie
    'credibility': 0.25,      # Ważne dla badań naukowych - wiarygodność źródła  
    'solidity': 0.20,         # Jakość i głębia treści
    'overall_usefulness': 0.20 # Ogólna użyteczność (mniejsza waga bo jest podsumowaniem innych)
}

@dataclass
class AssessmentResult:
    """Data class for storing assessment results."""
    relevance_score: int
    credibility_score: Optional[int]  # Can be None for research papers
    solidity_score: int
    overall_usefulness_score: int
    weighted_average_score: float
    llm_justification: str
    error_message: Optional[str] = None


class QualityAssessmentModule:
    """
    AI-powered quality assessment module for research results.
    
    Uses Google Gemini API to evaluate search results based on:
    - Relevance to original query
    - Source credibility
    - Content solidity
    - Overall usefulness for research
    """
    def __init__(self, database: Database, api_key: str = None, model_name: str = "gemini-2.5-flash-preview-05-20"):
        """
        Initialize the quality assessment module.
        
        Args:
            database: Database instance
            api_key: Google Gemini API key (or from environment)
            model_name: Gemini model to use (default: gemini-1.5-flash for cost efficiency)
        """
        self.database = database
        self.model_name = model_name
        
        # Configure Gemini API
        api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("Google Gemini API key not provided. Set GEMINI_API_KEY environment variable.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
          # Configuration for structured output
        self.generation_config = genai.types.GenerationConfig(
            temperature=0.2,  # Lower temperature for more consistent assessments
            max_output_tokens=3000,  # Increased from 1000 to handle longer responses
            response_mime_type="application/json",
            response_schema=AssessmentResponse
        )
        
        logger.info(f"QualityAssessmentModule initialized with model: {model_name}")

    def get_assessment_prompt(self, result_data: Dict[str, Any], initial_user_query: str) -> str:
        """
        Generate assessment prompt for LLM based on result data.
        
        Args:
            result_data: Dictionary containing query result information
            initial_user_query: The very first query provided by the user to the system.
            
        Returns:
            Formatted prompt string for LLM
        """        # specific_query_that_found_this_result = result_data.get('original_query_text', '') # This is the specific query
        title = result_data.get('title', 'No title available')
        snippet = result_data.get('snippet', 'No content preview available')
        source_type = result_data.get('source_type', 'unknown')
        domain = result_data.get('domain', 'Unknown domain')
        
        prompt = f"""You are a research assistant conducting a STRICT and CRITICAL assessment.
Your task is to assess the following search result for its usefulness.

INITIAL USER QUERY: "{initial_user_query}"

SEARCH RESULT TO ASSESS:
- Source Type: {source_type}
- Title: {title}
- Content Preview/Abstract: {snippet}
{f"- Domain: {domain}" if source_type == 'internet' else ""}

CRITICAL ASSESSMENT INSTRUCTIONS:
- Be EXTREMELY STRICT and CRITICAL in your evaluation
- Base your relevance assessment ONLY on what is visible in the "Content Preview/Abstract" section
- DO NOT assume any content beyond what is explicitly shown in the preview
- If the preview doesn't clearly and explicitly demonstrate relevance to the query, score it low
- Be skeptical - err on the side of lower scores rather than higher ones

ASSESSMENT CRITERIA (Rate each on scale 1-5, where 5 is excellent):

1. RELEVANCE SCORE: How directly related is the VISIBLE CONTENT to the INITIAL USER QUERY?
   CRITICAL: Judge ONLY based on the "Content Preview/Abstract" provided above.
   - 5: Preview explicitly addresses the query with specific, detailed examples directly matching the query terms
   - 4: Preview clearly mentions key terms from query and shows direct connection
   - 3: Preview shows some connection but lacks specificity or clear relevance
   - 2: Preview vaguely relates to query but connection is weak or unclear
   - 1: Preview shows no clear relevance or mentions query terms only in passing

2. CREDIBILITY SCORE: How trustworthy and authoritative is this source?
   FOR ACADEMIC PAPERS/RESEARCH SOURCES: Always set this to null (do not provide a number)
   
   FOR INTERNET SOURCES ONLY:
   - 5: Academic/government domains (.edu, .gov), major research institutions
   - 4: Established tech companies, well-known industry publications  
   - 3: Professional industry websites with clear authorship
   - 2: Personal blogs or lesser-known sources with identifiable authors
   - 1: Anonymous sources, suspicious domains, or unclear authorship

3. SOLIDITY SCORE: How substantial and well-written is the visible content?
   Based ONLY on the "Content Preview/Abstract":
   - 5: Comprehensive, technically detailed preview with specific information
   - 4: Good depth and clarity in preview, well-structured content
   - 3: Adequate information but lacking depth or clarity
   - 2: Basic information, vague or poorly structured preview
   - 1: Superficial, unclear, or very poorly written preview

4. OVERALL USEFULNESS SCORE: How valuable would this be for research based on the INITIAL USER QUERY?
   Consider ONLY what is visible in the preview - be conservative:
   - 5: Essential resource based on preview, clearly addresses research needs
   - 4: Very useful based on preview, strong potential value
   - 3: Moderately useful, some potential value visible in preview
   - 2: Limited usefulness, minimal value apparent from preview
   - 1: Not useful for research based on what's shown in preview

JUSTIFICATION: Provide a brief (1-2 sentences) explanation focusing specifically on why the visible content preview does or does not match the initial user query.

IMPORTANT: Be critical and conservative in your scoring. If there's any doubt about relevance or quality based on the preview alone, score lower rather than higher."""
        return prompt

    def assess_result(self, result_data: Dict[str, Any], initial_user_query: str, max_retries: int = 3) -> AssessmentResult:
        """
        Assess a single search result using LLM with structured output and retry mechanism.
        
        Args:
            result_data: Dictionary containing search result information
            initial_user_query: The very first query provided by the user to the system.
            max_retries: Maximum number of retry attempts
            
        Returns:
            AssessmentResult object with scores and justification        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                prompt = self.get_assessment_prompt(result_data, initial_user_query)
                
                response = self.model.generate_content(
                    prompt,
                    generation_config=self.generation_config
                )
                
                if not response.parts:
                    finish_reason_val = response.candidates[0].finish_reason if response.candidates and response.candidates[0].finish_reason else "UNKNOWN"
                    safety_ratings_val = response.candidates[0].safety_ratings if response.candidates and response.candidates[0].safety_ratings else []
                    
                    # Handle MAX_TOKENS finish reason by increasing max_output_tokens
                    if str(finish_reason_val) == "MAX_TOKENS" or finish_reason_val == 2:
                        error_msg = f"Content generation stopped due to MAX_TOKENS limit. Consider increasing max_output_tokens in generation_config."
                        logger.warning(error_msg)
                        last_error = error_msg
                        if attempt < max_retries - 1: time.sleep(1); continue
                        break
                    elif str(finish_reason_val) == "SAFETY" or finish_reason_val == 3:
                        error_msg = f"Content generation stopped due to safety reasons: {safety_ratings_val}"
                        logger.error(error_msg)
                        last_error = error_msg
                        if attempt < max_retries - 1: time.sleep(1); continue
                        break
                    else:
                        error_msg = f"No content part in response. Finish reason: {finish_reason_val}"
                        logger.error(error_msg)
                        last_error = error_msg
                        if attempt < max_retries - 1: time.sleep(1); continue
                        break
                
                assessment_pydantic: Optional[AssessmentResponse] = None
                if hasattr(response, 'parsed') and response.parsed:
                    if isinstance(response.parsed, AssessmentResponse):
                        assessment_pydantic = response.parsed
                    elif isinstance(response.parsed, list) and response.parsed and isinstance(response.parsed[0], AssessmentResponse):
                        assessment_pydantic = response.parsed[0]
                        logger.warning("LLM returned a list of assessments, using the first one.")
                    else:
                        logger.warning(f"response.parsed was not of type AssessmentResponse or list[AssessmentResponse], but {type(response.parsed)}. Trying response.text.")
                        assessment_pydantic = AssessmentResponse.model_validate_json(response.text)
                elif response.text:
                    logger.warning("response.parsed was not available or empty. Falling back to response.text and Pydantic validation.")
                    assessment_pydantic = AssessmentResponse.model_validate_json(response.text)
                else:
                    # This case should ideally be caught by 'if not response.parts:'
                    last_error = "Response has no 'parsed' attribute and no 'text'. Cannot extract assessment."
                    logger.error(last_error)
                    if attempt < max_retries - 1: time.sleep(1); continue
                    break
                
                if assessment_pydantic is None: # Should not happen if logic above is correct
                    last_error = "Failed to extract AssessmentResponse object from LLM response."
                    logger.error(last_error)
                    if attempt < max_retries - 1: time.sleep(1); continue
                    break
                
                # Set credibility_score to None for research papers (as per system requirements)
                credibility_score = assessment_pydantic.credibility_score
                if result_data.get('source_type') == 'research_paper':
                    credibility_score = None
                
                # Calculate weighted average score
                weighted_avg = self.calculate_weighted_average(
                    assessment_pydantic.relevance_score,
                    credibility_score,
                    assessment_pydantic.solidity_score,
                    assessment_pydantic.overall_usefulness_score
                )

                return AssessmentResult(
                    relevance_score=assessment_pydantic.relevance_score,
                    credibility_score=credibility_score,
                    solidity_score=assessment_pydantic.solidity_score,
                    overall_usefulness_score=assessment_pydantic.overall_usefulness_score,
                    weighted_average_score=weighted_avg,
                    llm_justification=assessment_pydantic.llm_justification,
                )
            except (json.JSONDecodeError, ValidationError) as e: 
                last_error = f"Failed to validate/parse LLM response (attempt {attempt + 1}/{max_retries}): {e}"
                logger.warning(f"{last_error}. Response text: {response.text[:300] if response.text else 'N/A'}...")
                if attempt < max_retries - 1: time.sleep(1); continue
                break
            except AttributeError as e: 
                last_error = f"Unexpected response structure (attempt {attempt + 1}/{max_retries}): {e}. Response: {response}"
                logger.warning(last_error)
                if attempt < max_retries - 1: time.sleep(1); continue
                break
            except Exception as e: 
                if hasattr(e, 'message') and isinstance(e.message, str): 
                    last_error = f"Google API Error (attempt {attempt + 1}/{max_retries}): {e.message}"
                else:
                    last_error = f"Unexpected error during assessment (attempt {attempt + 1}/{max_retries}): {e}"
                logger.error(last_error)
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                break        
        error_msg = last_error or "Unknown error during assessment after all retries"
        logger.error(f"All retry attempts failed for result_data: {result_data.get('query_result_id')}. Final error: {error_msg}")
        return AssessmentResult(
            relevance_score=0, credibility_score=None, solidity_score=0,
            overall_usefulness_score=0, weighted_average_score=0.0,
            llm_justification="", error_message=error_msg
        )

    def save_assessment(self, query_result_id: int, initial_user_query: str, 
                       assessment_prompt: str, llm_response_raw: str, 
                       assessment: AssessmentResult) -> int:
        """
        Save assessment results to database.
        
        Args:
            query_result_id: ID of the query result
            initial_user_query: The initial query from the user.
            assessment_prompt: The prompt sent to LLM
            llm_response_raw: Raw response from LLM (or parsed Pydantic model as str)
            assessment: AssessmentResult object
            
        Returns:
            ID of the created assessment record
        """
        return self.database.update_or_create_assessment(
            query_result_id=query_result_id,
            original_query_text=initial_user_query, # Store the initial user query
            assessment_prompt=assessment_prompt,
            llm_response_raw=llm_response_raw,
            relevance_score=assessment.relevance_score if assessment.relevance_score and assessment.relevance_score > 0 else None,
            credibility_score=assessment.credibility_score if assessment.credibility_score is not None and assessment.credibility_score > 0 else None,
            solidity_score=assessment.solidity_score if assessment.solidity_score and assessment.solidity_score > 0 else None,
            overall_usefulness_score=assessment.overall_usefulness_score if assessment.overall_usefulness_score and assessment.overall_usefulness_score > 0 else None,            weighted_average_score=assessment.weighted_average_score if assessment.weighted_average_score and assessment.weighted_average_score > 0 else None,
            llm_justification=assessment.llm_justification,
            error_message=assessment.error_message
        )

    def run_assessment_workflow(self, batch_size: Optional[int] = None, delay_between_calls: float = 1.0) -> Dict[str, Any]:
        """
        Run the complete assessment workflow on unassessed results.
        
        Args:
            batch_size: Number of results to process in this run (None = process all unassessed results)
            delay_between_calls: Delay in seconds between API calls to avoid rate limits
            
        Returns:
            Dictionary with workflow statistics
        """
        logger.info(f"Starting quality assessment workflow (batch_size: {batch_size or 'ALL'})")
        
        unassessed_results = self.database.get_unassessed_query_results(limit=batch_size)
        
        if not unassessed_results:
            logger.info("No unassessed results found")
            return {
                'processed_count': 0,
                'success_count': 0,
                'error_count': 0,
                'errors': []
            }
        
        logger.info(f"Found {len(unassessed_results)} unassessed results to process")
        
        processed_count = 0
        success_count = 0
        error_count = 0
        errors = []
        
        for i, result_data in enumerate(unassessed_results):
            try:
                query_result_id = result_data['query_result_id']                # Use the original query text specific to this result
                original_query_text = result_data.get('original_query_text', 'Unknown query')
                
                logger.info(f"Processing result {i+1}/{len(unassessed_results)}: ID {query_result_id} for query: '{original_query_text}'")
                
                assessment_prompt = self.get_assessment_prompt(result_data, original_query_text)
                assessment = self.assess_result(result_data, original_query_text)
                
                raw_response_to_store = assessment.llm_justification
                if assessment.error_message:
                    raw_response_to_store = f"ERROR: {assessment.error_message}"

                assessment_id = self.save_assessment(
                    query_result_id=query_result_id,
                    initial_user_query=original_query_text,
                    assessment_prompt=assessment_prompt,
                    llm_response_raw=raw_response_to_store,
                    assessment=assessment
                )
                
                if assessment.error_message:
                    error_count += 1
                    errors.append({
                        'query_result_id': query_result_id,
                        'error': assessment.error_message
                    })
                    logger.error(f"Assessment error for result {query_result_id}: {assessment.error_message}")
                else:
                    success_count += 1
                    logger.info(f"Successfully assessed result {query_result_id} "
                              f"(usefulness: {assessment.overall_usefulness_score}/5)")
                
                processed_count += 1
                
                # Add delay between API calls
                if delay_between_calls > 0 and i < len(unassessed_results) - 1:
                    time.sleep(delay_between_calls)
                    
            except Exception as e:
                error_count += 1
                error_msg = f"Unexpected error processing result {result_data.get('query_result_id', 'unknown')}: {e}"
                errors.append({
                    'query_result_id': result_data.get('query_result_id', 'unknown'),
                    'error': error_msg
                })
                logger.error(error_msg)
                processed_count += 1
        
        workflow_stats = {
            'processed_count': processed_count,
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors
        }
        
        logger.info(f"Assessment workflow completed: {workflow_stats}")
        return workflow_stats

    def get_assessment_statistics(self) -> Dict[str, Any]:
        """Get statistics about completed assessments."""
        stats = {}
        
        # Total assessments
        all_assessments = self.database.get_all_assessments()
        stats['total_assessments'] = len(all_assessments)
        
        if stats['total_assessments'] == 0:
            return stats
        
        # Count by score ranges
        stats['score_distribution'] = self.database.count_assessments_by_score()
        
        # High-value results (usefulness >= 4)
        high_value = self.database.get_assessments_by_score_range(min_usefulness=4, max_usefulness=5)
        stats['high_value_results'] = len(high_value)
        
        # Average scores
        scores = {
            'relevance': [a['relevance_score'] for a in all_assessments if a['relevance_score']],
            'credibility': [a['credibility_score'] for a in all_assessments if a['credibility_score']],
            'solidity': [a['solidity_score'] for a in all_assessments if a['solidity_score']],
            'usefulness': [a['overall_usefulness_score'] for a in all_assessments if a['overall_usefulness_score']]
        }
        
        stats['average_scores'] = {}
        for category, score_list in scores.items():
            if score_list:
                stats['average_scores'][category] = round(sum(score_list) / len(score_list), 2)
            else:
                stats['average_scores'][category] = 0.0
        
        # Error rate
        error_assessments = [a for a in all_assessments if a.get('error_message')]
        stats['error_count'] = len(error_assessments)
        stats['error_rate'] = round(len(error_assessments) / len(all_assessments) * 100, 2) if all_assessments else 0
        
        return stats

    def calculate_weighted_average(self, relevance_score: int, credibility_score: Optional[int], 
                             solidity_score: int, overall_usefulness_score: int) -> float:
        """
        Calculate weighted average score based on predefined weights.
        When credibility_score is None (for research papers), we redistribute its weight
        proportionally among the other scores.
        
        Args:
            relevance_score: Relevance to query (1-5)
            credibility_score: Source credibility (1-5) or None for research papers
            solidity_score: Content quality (1-5)
            overall_usefulness_score: Overall usefulness (1-5)
            
        Returns:
            Weighted average score (1.0-5.0)
        """
        # Validate non-null scores
        scores_to_validate = [relevance_score, solidity_score, overall_usefulness_score]
        if credibility_score is not None:
            scores_to_validate.append(credibility_score)
            
        if not all(1 <= score <= 5 for score in scores_to_validate):
            raise ValueError("All scores must be between 1 and 5")
        
        if credibility_score is not None:
            # Standard calculation with all scores
            weighted_sum = (
                relevance_score * ASSESSMENT_WEIGHTS['relevance'] +
                credibility_score * ASSESSMENT_WEIGHTS['credibility'] +
                solidity_score * ASSESSMENT_WEIGHTS['solidity'] +
                overall_usefulness_score * ASSESSMENT_WEIGHTS['overall_usefulness']
            )
        else:
            # Redistribute credibility weight proportionally among other scores
            # New weights when credibility is excluded
            total_remaining_weight = (ASSESSMENT_WEIGHTS['relevance'] + 
                                    ASSESSMENT_WEIGHTS['solidity'] + 
                                    ASSESSMENT_WEIGHTS['overall_usefulness'])
            
            # Calculate redistribution factor
            redistribution_factor = 1.0 / total_remaining_weight
            
            adjusted_weights = {
                'relevance': ASSESSMENT_WEIGHTS['relevance'] * redistribution_factor,
                'solidity': ASSESSMENT_WEIGHTS['solidity'] * redistribution_factor,
                'overall_usefulness': ASSESSMENT_WEIGHTS['overall_usefulness'] * redistribution_factor
            }
            
            weighted_sum = (
                relevance_score * adjusted_weights['relevance'] +
                solidity_score * adjusted_weights['solidity'] +
                overall_usefulness_score * adjusted_weights['overall_usefulness']
            )
        
        return round(weighted_sum, 2)


def main():
    """Example usage of the QualityAssessmentModule."""
    # This is for testing - in production, this would be called from main workflow
    
    import argparse
    parser = argparse.ArgumentParser(description='Run quality assessment on search results')
    parser.add_argument('--batch-size', type=int, default=None, help='Number of results to process (default: all unassessed results)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between API calls in seconds')
    parser.add_argument('--database-path', type=str, default='data/research_db.db', help='Path to database file')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Initialize database and assessment module
        database = Database(db_path=args.database_path)
        assessment_module = QualityAssessmentModule(database)
        
        # Run assessment workflow
        results = assessment_module.run_assessment_workflow(
            batch_size=args.batch_size,
            delay_between_calls=args.delay
        )
        
        print(f"\n=== Assessment Workflow Results ===")
        print(f"Processed: {results['processed_count']}")
        print(f"Success: {results['success_count']}")
        print(f"Errors: {results['error_count']}")
        
        if results['errors']:
            print("\nErrors encountered:")
            for error in results['errors']:
                print(f"  - Result ID {error['query_result_id']}: {error['error']}")
        
        # Show statistics
        stats = assessment_module.get_assessment_statistics()
        print(f"\n=== Assessment Statistics ===")
        print(json.dumps(stats, indent=2))
        
    except Exception as e:
        logger.error(f"Failed to run assessment workflow: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
