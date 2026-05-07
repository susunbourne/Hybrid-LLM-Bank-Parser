from bank_parser import find_pdf_files, get_bank_config, StatementProcessor
from pathlib import Path
import pandas as pd
from collections import Counter

import os
from database import DatabaseManager
from dotenv import load_dotenv
from classifier import TransactionClassifier, GeminiBackend, OpenAIBackend, DeepSeekBackend, ClassificationResult


def main() -> None:
    load_dotenv()

    print("Starting the bank statement processing...")
    print("What kind of statements do you want to process?")
    print("1. Bank of America")
    print("2. Bank of America Credit Card")
    choice = input("Enter the number corresponding to your choice: ")

    if choice == "1":
        config_to_use, directory_path, output_path = get_bank_config("Bank of America")
    elif choice == "2":
        config_to_use, directory_path, output_path = get_bank_config("Bank of America Credit Card")
    else:
        raise ValueError("Invalid choice. Please enter 1 or 2.")

    pdf_files_to_process = find_pdf_files(directory_path)

    if not pdf_files_to_process:
        print("No PDF files found in the specified directory.")
        return

    print("Processing the following PDF files:")
    all_dataframes = []

    for pdf_file in pdf_files_to_process:
        print(f"Processing {pdf_file.name}...")
        try:
            processor = StatementProcessor(pdf_file, config_to_use)
            df = processor.process()
            if not df.empty:
                all_dataframes.append(df)
            else:
                print(f"No transactions found in {pdf_file.name}.")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {e}")

    if not all_dataframes:
        print("No transactions found in any PDF files.")
        return

    print("Combining all dataframes...")
    combined_df = pd.concat(all_dataframes, ignore_index=True)

    # 分类
    print("Classifying transactions...")
    classifier = TransactionClassifier(
        backend=DeepSeekBackend(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model="deepseek-chat"
        )
    )

    results: list[ClassificationResult] = []
    for _, row in combined_df.iterrows():
        result = classifier.classify(row["description"])
        results.append(result)

    combined_df["category_main"]         = [r.category_main for r in results]
    combined_df["category_sub"]          = [r.category_sub or "" for r in results]
    combined_df["classification_method"] = [r.classification_method or "" for r in results]

    # 统计
    total     = len(results)
    success   = [r for r in results if r.category_main not in ("Empty", "Nonsense", "Uncertain")]
    failed    = [r for r in results if r.category_main in ("Empty", "Nonsense")]
    uncertain = [r for r in results if r.category_main == "Uncertain"]
    method_counts = Counter(r.classification_method for r in success)

    print(f"成功: {len(success)}/{total}")
    print(f"失败: {len(failed)}")
    print(f"不确定: {len(uncertain)}")
    print(f"各层命中: {dict(method_counts)}")

    # 写库
    db_host     = os.getenv("DB_HOST", "localhost")
    db_port     = int(os.getenv("DB_PORT", "3307"))
    db_user     = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "")
    db_name     = os.getenv("DB_NAME", "budget_manager")

    try:
        db = DatabaseManager(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        db.create_database()
        db.ensure_transactions_table()
        inserted_rows = db.insert_transactions_from_df(combined_df, config_to_use.bank_name)
        print(f"Inserted {inserted_rows} transactions into the database.")
    except Exception as e:
        print(f"Database error: {e}")

    combined_df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}.")


if __name__ == "__main__":
    main()