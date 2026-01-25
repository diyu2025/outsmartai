#!/usr/bin/env python3
"""
Download FormalGeo datasets for testing

This script downloads the formalgeo7k_v1 dataset needed for the grader.
"""

import sys
from pathlib import Path

# Add FormalGeo to path if needed
formalgeo_path = "/Users/yud/repo/FormalGeo"
if str(formalgeo_path) not in sys.path:
    sys.path.insert(0, formalgeo_path)

def download_datasets():
    """Download FormalGeo datasets"""
    try:
        from formalgeo.data import download_dataset, show_available_datasets
        
        datasets_path = "/Users/yud/repo/formalgeo7k/datasets"
        Path(datasets_path).mkdir(parents=True, exist_ok=True)
        
        print(f"Datasets will be downloaded to: {datasets_path}\n")
        
        print("Available datasets:")
        show_available_datasets(datasets_path)
        
        print("\n" + "="*80)
        print("Downloading formalgeo7k_v1...")
        print("="*80 + "\n")
        
        download_dataset(
            dataset_name="formalgeo7k_v1",
            datasets_path=datasets_path
        )
        
        print("\n✅ Dataset downloaded successfully!")
        print(f"   Location: {datasets_path}/formalgeo7k_v1")
        
    except Exception as e:
        print(f"❌ Failed to download dataset: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = download_datasets()
    sys.exit(0 if success else 1)
