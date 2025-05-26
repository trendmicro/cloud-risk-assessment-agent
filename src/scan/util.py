import subprocess
import os
import sys
import io
import json
import tiktoken
import json
import pandas as pd
from prettytable import PrettyTable
from importlib import resources

# Filter rows based on severity
def filter_severity(df, severity_levels, min_count=5):
    filtered_df = df[df["Severity"].isin(severity_levels)]
    return filtered_df if len(filtered_df) >= min_count else None

def sanitize_input(input_text: str) -> str:
    # Example: Remove problematic characters or replace them
    return input_text.replace("{", "{{").replace("}", "}}").replace("%", "%%")


def count_gpt_tokens(text, model_name="gpt-4o"):
    # Initialize the encoder for the specified model
    encoder = tiktoken.encoding_for_model(model_name)

    # Encode the text into tokens
    tokens = encoder.encode(text)

    # Return the number of tokens
    return len(tokens)

class NoOutputError(Exception):
    """Exception raised when the expected output file is not found."""
    def __init__(self, filename):
        self.filename = filename
        self.message = f"Output file '{filename}' not found. Command may have failed to create it."
        super().__init__(self.message)

class JSONParseError(Exception):
    """Exception raised when a JSON file cannot be parsed."""

    def __init__(self, filename):
        self.filename = filename
        self.message = f"Failed to parse JSON file '{filename}'."
        super().__init__(self.message)

def run_command_and_read_output(command: list, output_file: str) -> dict:
    subprocess.run(command, check=True)
    if os.path.exists(output_file):
        with open(output_file, "r") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                raise JSONParseError(output_file)
    else:
        raise NoOutputError(output_file)


def extract_code_to_buffer(file_path, start_line, end_line):
    """
    Extracts lines from start_line to end_line (inclusive) from the file at file_path
    and returns them as a StringIO buffer.

    :param file_path: Path to the source text file.
    :param start_line: The starting line number (1-based index).
    :param end_line: The ending line number (inclusive, 1-based index).
    :return: A StringIO buffer containing the extracted lines.
    """
    extracted_lines = []

    with open(file_path, 'r') as file:
        for current_line_number, line in enumerate(file, start=1):
            if start_line <= current_line_number <= end_line:
                extracted_lines.append(line)
            elif current_line_number > end_line:
                break

    return ''.join(extracted_lines)


def get_severity(input_level):
    levels = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    try:
        if input_level not in levels:
            raise ValueError(f"Invalid level: {input_level}")
        start_index = levels.index(input_level)
        return levels[start_index:]
    except ValueError as e:
        print(e)
        return ["HIGH", "CRITICAL"]

def run_command(command: list, output_file: str):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)

    if os.path.exists(output_file):
        return True, result.stdout
    else:
        return False, result.stdout

def run_command_bg(command: list):
    process = subprocess.Popen(
        command,
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    return process
