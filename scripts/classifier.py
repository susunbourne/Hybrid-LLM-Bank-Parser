import os
import json
import re 
import logging
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass,asdict
from typing import Optional
from difflib import SequenceMatcher
from abc import ABC, abstractmethod

from dotenv import load_dotenv
from google import genai
from openai import OpenAI


logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

# LLM Classifier interface

class LLMClassifier(ABC):
    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        ...

class GeminiBackend(LLMClassifier):
    def __init__(self, api_key: str, model: str):
        self.client = genai.Client(api_key = api_key)
        self.model = model
        

    def generate_response(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model = self.model,
            contents = prompt,
            config = {
                "temperature" : 0,
                "response_mime_type" : "application/json"
            }
        )
        return (response.text or "").strip()
    
class OpenAIBackend(LLMClassifier):
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(api_key = api_key)
        self.model = model        
    def generate_response(self, prompt: str) -> str:
        response = self.client.responses.create(
            model = self.model,
            temperature = 0,
            response_format = {
                "type" : "json_object"},
            input = [
                {"role": "system", "content":"Output valid JSON  only"},
                {"role": "user", "content": prompt},
            ],
        )

        return (response.choices[0].message.content or "").strip()
    
class DeepSeekBackend(LLMClassifier):
    def __init__(self, api_key: str, model: str):
        self.client = OpenAI(
            api_key = api_key,
            base_url = "https://api.deepseek.com",
            
        )
        self.model = model
    


    def generate_response(self, prompt):
        response = self.client.chat.completions.create(
            model = self.model,
            messages = [
                {"role": "system", "content":"Output valid JSON  only"},
                {"role": "user", "content": prompt},
            ],
            stream = False

        )
        return (response.choices[0].message.content or "").strip()
    

# Dataclass

# @dataclass
# class ClassificationExample:
#     description: str
#     category_main: str
#     category_sub: Optional[str] = None


@dataclass
class ClassificationResult:
    category_main: str
    description: Optional[str] = None

    category_sub: Optional[str] = None
    classification_method: Optional[str] = None
    raw_response: Optional[str] = None



# Classifier
class TransactionClassifier:
    MAIN_CATEGORIES = [
        "Food & Dining",
        "Transportation",
        "Housing",
        "Entertainment",
        "Shopping",
        "Education",
        "Health & Fitness",
        "Financial Investments",
        "International Transactions",
        "Domestic Transactions",
        "Credit Card Payments",
        "Part-time Job Income",
        "Other"
    ]

    KEYWORD_RULES: dict[str, list[str]] = {
        "Food & Dining": (
            ["starbucks", "mcdonald", "uber eats", "doordash", "grubhub",
             "chipotle", "subway", "pizza", "restaurant", "cafe", "coffee",
             "dining", "food", "lunch", "dinner", "breakfast"]
        ),
        "Transportation": (
            ["lyft", "taxi", "gas station", "shell", "bp", "chevron",
             "exxon", "parking", "metro", "transit", "amtrak", "delta",
             "united airlines", "southwest", "flight"]
        ),
        "Shopping": (
            ["amazon", "walmart", "target", "costco", "ebay", "etsy",
             "bestbuy", "best buy", "apple store", "ikea", "zara", "h&m"]
        ),
        "Health & Fitness": (
            ["pharmacy", "cvs", "walgreens", "rite aid", "gym", "planet fitness",
             "doctor", "dental", "hospital", "clinic", "health"]
        ),
        "Entertainment": (
            ["netflix", "spotify", "hulu", "disney", "steam", "playstation",
             "xbox", "cinema", "movie", "concert", "ticketmaster"]
        ),
        "Education": (
            ["tuition", "coursera", "udemy", "textbook", "university",
             "college", "school", "library", "course"]
        ),
        "Credit Card Payments": (
            ["credit card payment", "card payment", "autopay", "minimum payment"]
        ),
        "Part-time Job Income": (
            ["payroll", "direct deposit", "salary", "wage", "stipend",
             "venmo from", "zelle from", "paycheck"]
        ),
    }
    def __init__(
            self,
            backend: Optional[LLMClassifier] = None,
            max_retries: int = 3,
            retry_delay: float = 1.0,
            #examples_file: Path = Path("classification_examples.json"),
        
    ):
        self.backend = backend
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        #self.examples: list[ClassificationExample] = []
        #self.examples_file = examples_file
        #self._load_examples()
        self.cache = {}

    def _build_prompt(self, description: str) -> str:
        category_text = ", ".join(self.MAIN_CATEGORIES)
        return f"""You are a personal finance transaction classifier.
Return exactly one JSON object.
Do not output explanations, markdown, or code fences.

category_main must be EXACTLY one of:
{category_text}

If uncertain, use "uncertain".
category_sub should be one sentence short and specific.

Transaction description: {description}

Output valid JSON only:
{{
  "category_main": "one value from the list above",
  "category_sub": "short subcategory"
}}"""
    
    def _call_llm_with_retry(self, prompt: str)-> str:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return self.backend.generate_response(prompt)
            except Exception as e:
                last_error = e
                wait = self.retry_delay * (attempt + 1)
                logger.warning(f"LLM attempt {attempt + 1} failed: {e}. Retrying in {wait} seconds...")
                time.sleep(wait)
        raise RuntimeError(f"LLM failed after {self.max_retries + 1} attempts: {last_error}")
    
    def _parse_and_validate(self, raw_text: str) -> Optional[ClassificationResult]:
        if not raw_text:
            logger.warning("LLM returned empty response")
            return ClassificationResult(
            category_main = "Empty",
            )
        try:
            payload = json.loads(raw_text)
        except Exception as e:
            match = re.search(r"\{[\s\S]*\}", raw_text)

            if not match:
                logger.warning(f"LLM response does not contain valid JSON: {raw_text}")
                return ClassificationResult(
                    category_main = "Nonsense",
                    raw_response = raw_text
                )
            try:
                payload = json.loads(match.group(0))
            except Exception as e2:
                logger.warning(f"Failed to parse JSON from LLM response: {e2}")
                return ClassificationResult(
                    category_main = "Nonsense",
                    raw_response = raw_text
                )
        category_main = payload.get("category_main").strip()

        if category_main not in self.MAIN_CATEGORIES:
            category_main = "Uncertain"

        category_sub = payload.get("category_sub")
        if len(category_sub) > 35:
            category_sub = category_sub[:35]
        return ClassificationResult(
            category_main = category_main,
            category_sub = category_sub,
            raw_response = raw_text
        )
    
    # Keyword rules

    def _keyword_match(self, description: str) -> Optional[ClassificationResult]:
        desc_lower = description.lower()
        for category, keyword in self.KEYWORD_RULES.items():
            for kw in keyword:
                if " " in kw:
                    if kw in desc_lower:
                        return ClassificationResult(
                            category_main = category,
                            classification_method = "keyword"
                        )
                else:
                    if re.search(rf"\b{re.escape(kw)}\b", desc_lower):
                        return ClassificationResult(
                            category_main = category,
                            classification_method = "keyword"
                        )
        return ClassificationResult(
            category_main = "Uncertain",
            classification_method = "keyword"
        )


    def classify(self, description: str) -> ClassificationResult:
        if description in self.cache:
            return self.cache[description]
        if not description:
            result = ClassificationResult(
                description = description,
                category_main = "Empty",
                classification_method = "none"
            )
            self.cache[description] = result
            return result
        if self.backend:
            try:

                prompt = self._build_prompt(description)
                raw_response = self._call_llm_with_retry(prompt)
                parsed = self._parse_and_validate(raw_response)

                if parsed and parsed.category_main not in ["Nonsense", "Uncertain", "Empty"]:
                    parsed.classification_method = "LLM"
                    self.cache[description] = parsed
                    return parsed
            except Exception as e:
                logger.error(f"LLM classification failed: {e}")
        
        keyword_result = self._keyword_match(description)
        self.cache[description] = keyword_result
        return keyword_result

        
        



_classifier_instance = None

def get_classifier() -> TransactionClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = TransactionClassifier(
            backend = DeepSeekBackend(
                api_key = os.getenv("DEEPSEEK_API_KEY"),
                model = "deepseek-chat"
            )
        )

    return _classifier_instance




