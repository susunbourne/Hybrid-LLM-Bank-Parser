from dataclasses import dataclass
from functools import cached_property
import re
import pandas as pd
import pdftotext
import os
from pathlib import Path

@dataclass
class BankConfig:
    bank_name: str
    transaction_pattern: str
    category_keywords: dict[str, list[str]]


bank_of_america_config = BankConfig(
    bank_name = "Bank of America",
    transaction_pattern = (    
    r"(?P<transaction_date>\d+/\d+/\d+)\s*"
    r"(?P<description>.*?)\s*"
    r"(?P<amount>-?[\d.,]+(?:\.\d{2})?)$"),
    category_keywords = {
            'Food': ['food', 'food lion', 'restaurant', 'grocery', 'bojangles', 'target', 'liming',],
            'Investment':['ibkr', 'interactive brokers', 'stock', 'investment','interactive'],
            'Credit Card': ['credit card', 'visa', 'mastercard', 'amex','7801'],
            'rent': ['rent', 'chapel ridge', 'rent payment'],
            'transfer': ['wire', 'wire transfer', 'transfer', 'zelle'],
            'tuitonfee': ['unc student', 'tuition']
            }
)

bank_of_america_cc_config = BankConfig(
    bank_name = "Bank of America Credit Card",
    transaction_pattern = (
        r"(?P<transaction_date>\d+/\d+)\s*"
        r"(?: \d+/\d+\s+)?"
        r"(?P<description>.*?)\s+"
        r"(?P<amount>-?[\d.,]+(?:\.\d{2})?)$"
    ),
    category_keywords = {
            'Food': ['food', 'food lion', 'restaurant', 'grocery', 'bojangles', 'target', 'liming',],
            'Investment':['ibkr', 'interactive brokers', 'stock', 'investment'],
            'rent': ['rent', 'chapel ridge', 'rent payment'],
            'transfer': ['wire', 'wire transfer', 'transfer'],
            'Credit Card': ['credit card', 'visa', 'mastercard', 'amex','7801'],
    }
)


class PdfParser:
    def __init__(self, file_path: Path, config: BankConfig):
        self.file_path = file_path
        self.config = config

    @cached_property
    def pdf(self) -> list[str]:
        with open(self.file_path, "rb") as f:
            pdf = pdftotext.PDF(f, physical = True)
        return pdf
    
    @cached_property
    def transactions(self) -> list[dict]:
        transactions = []
        transactions_pattern = self.config.transaction_pattern
        for page_num, page in enumerate(self.pdf, start = 1):
            lines = page.split("\n")
            for line in lines:
                line = line.strip()
                match = re.search(transactions_pattern, line)
                if match:
                    transactions.append(match.groupdict())
        return transactions

class StatementProcessor(PdfParser):
    def __init__(self, file_path: Path, config: BankConfig):
        super().__init__(file_path, config)

    def extract(self) -> pd.DataFrame:
        return pd.DataFrame(self.transactions)
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.config.bank_name == "Bank of America Credit Card":
            current_year = pd.Timestamp.now().year
            df["transaction_date"] = df["transaction_date"].apply(lambda x: f"{x}/{current_year}")
        df["transaction_date"] = pd.to_datetime(df['transaction_date'], format = "mixed")
        df["amount"] = df["amount"].str.replace(",", "")
        df["amount"] = df["amount"].astype(float)
        if "credit card" in self.config.bank_name.lower():
            df["amount"] = df["amount"] * (-1)
        return df
    def load(self, df:pd.DataFrame,):
        df.to_csv("processed_statements.csv", index = False)
    def sort_by_date(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.sort_values(by="transaction_date", ascending = True)
    
    def categorize(self, description: str) -> str:
        desc = description.lower()
        for cat, keywords in self.config.category_keywords.items():
            if any(keyword in desc for keyword in keywords):
                return cat
        return 'Other'
    
    def process(self) -> pd.DataFrame:
        df = self.extract()
        df = self.transform(df)
        df = self.sort_by_date(df)
        #df['category_main'] = df['description'].apply(self.categorize)
        return df

def find_pdf_files(directory_path: Path) -> list[Path]:
    input_path = Path(directory_path)
    pdf_files = list(input_path.glob("*.pdf"))

    return pdf_files

def get_bank_config(bank_name: str) -> BankConfig:
    if bank_name.lower() == "bank of america":
        input_path = os.getenv("BANK_INPUT_PATH")
        output_path = Path(os.getenv("OUTPUT_PATH")) / "bank_parser_output.csv"
        return bank_of_america_config, input_path, output_path
    elif bank_name.lower() == "bank of america credit card":
        input_path = os.getenv("CREDIT_CARD_STATEMENT_PATH")
        output_path = Path(os.getenv("OUTPUT_PATH")) / "bank_parser_cc_output.csv"
        return bank_of_america_cc_config, input_path, output_path
    else:
        raise ValueError(f"Unsupported bank name: {bank_name}")