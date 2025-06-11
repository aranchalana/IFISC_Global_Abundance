#!/usr/bin/env python3
"""
Simple reference-based species data extraction.
OUTPUT: CSV with columns: doi, species, abundance_or_biomass, number, location, distance_from_seed, title
"""

import os
import requests
import pandas as pd
import time
import argparse
import csv
import re
import json
from typing import List, Dict, Any
import PyPDF2
import pdfplumber

def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF file"""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n".join(text_parts)
    except:
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text_parts = []
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                return "\n".join(text_parts)
        except:
            return ""

def extract_species_from_text(text: str, doi: str, title: str, distance: int, claude_api_key: str) -> List[Dict]:
    """Extract species data using Claude API"""
    
    headers = {
        "x-api-key": claude_api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    
    prompt = f"""
    Extract species information from this research paper. Return ONLY a JSON array.

    For each species in the study, extract:
    - species: scientific name (Genus species)
    - abundance_or_biomass: population data, density, biomass measurements
    - number: specimen count or sample size
    - location: study location or habitat

    Return format:
    [
      {{
        "species": "Genus species",
        "abundance_or_biomass": "density/biomass data or not specified",
        "number": "count or not specified", 
        "location": "location"
      }}
    ]

    Text: {text[:40000]}
    """
    
    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload, 
            timeout=60
        )
        response.raise_for_status()
        
        response_data = response.json()
        claude_response = response_data["content"][0]["text"]
        
        # Parse JSON response
        claude_response = re.sub(r'```(?:json)?\n', '', claude_response)
        claude_response = re.sub(r'\n```', '', claude_response)
        
        json_match = re.search(r'(\[.*\]|\{.*\})', claude_response, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            json_text = claude_response
        
        result = json.loads(json_text)
        if isinstance(result, dict):
            result = [result]
        
        # Format results
        species_data = []
        for item in result:
            if isinstance(item, dict):
                species_data.append({
                    'doi': doi,
                    'species': str(item.get('species', 'UNSPECIFIED')).strip(),
                    'abundance_or_biomass': str(item.get('abundance_or_biomass', 'not specified')).strip(),
                    'number': str(item.get('number', 'not specified')).strip(),
                    'location': str(item.get('location', 'UNSPECIFIED')).strip(),
                    'distance_from_seed': distance,
                    'title': title.strip()
                })
        
        return species_data
        
    except Exception as e:
        print(f"    Error extracting species: {e}")
        return []

def get_paper_references(doi: str, scopus_api_key: str) -> List[Dict]:
    """Get references from Scopus"""
    
    headers = {
        'X-ELS-APIKey': scopus_api_key,
        'Accept': 'application/json'
    }
    
    try:
        # Find Scopus ID
        response = requests.get(
            "https://api.elsevier.com/content/search/scopus",
            headers=headers,
            params={
                'query': f'DOI("{doi}")',
                'count': 1,
                'field': 'dc:identifier'
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        entries = data.get('search-results', {}).get('entry', [])
        if not entries:
            return []
        
        scopus_id = entries[0].get('dc:identifier', '').replace('SCOPUS_ID:', '')
        if not scopus_id:
            return []
        
        print(f"    Found Scopus ID: {scopus_id}")
        
        # Get references - simplified field list
        refs_response = requests.get(
            f"https://api.elsevier.com/content/abstract/scopus_id/{scopus_id}/references",
            headers=headers,
            params={
                'count': 20
            },
            timeout=30
        )
        
        if refs_response.status_code == 400:
            print(f"    References endpoint failed, trying alternative approach...")
            return []
        
        refs_response.raise_for_status()
        
        refs_data = refs_response.json()
        
        # Navigate the response structure
        abstract_response = refs_data.get('abstract-retrieval-response', {})
        references_section = abstract_response.get('references', {})
        
        if isinstance(references_section, dict):
            references = references_section.get('reference', [])
        else:
            references = references_section
        
        if not isinstance(references, list):
            references = [references] if references else []
        
        # Process references with better error handling
        ref_papers = []
        for ref in references:
            try:
                # Multiple ways to extract reference info
                ref_info = ref.get('ref-info', {})
                
                # Try to get DOI
                ref_doi = ""
                if 'ref-publicationtitle' in ref_info:
                    pub_title_info = ref_info['ref-publicationtitle']
                    if isinstance(pub_title_info, dict):
                        ref_doi = pub_title_info.get('prism:doi', '')
                
                # Try to get title
                ref_title = ""
                if 'ref-title' in ref_info:
                    title_info = ref_info['ref-title']
                    if isinstance(title_info, dict):
                        ref_title = title_info.get('ref-titletext', '')
                    elif isinstance(title_info, str):
                        ref_title = title_info
                
                # Alternative title extraction
                if not ref_title and 'ref-titletext' in ref_info:
                    ref_title = ref_info.get('ref-titletext', '')
                
                # Only add if we have both DOI and title
                if ref_doi and ref_title and len(ref_title) > 10:
                    ref_papers.append({'doi': ref_doi, 'title': ref_title})
                    
            except Exception as e:
                # Skip problematic references
                continue
        
        print(f"    Successfully extracted {len(ref_papers)} references")
        return ref_papers[:10]  # Limit to 10 references
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            print(f"    Bad request for references - paper may not have accessible references")
        elif e.response.status_code == 404:
            print(f"    Paper not found in Scopus")
        else:
            print(f"    HTTP error getting references: {e}")
        return []
    except Exception as e:
        print(f"    Error getting references: {e}")
        return []

def search_papers_by_title(title: str, scopus_api_key: str, max_results: int = 10) -> List[Dict]:
    """Search Scopus by title to find related papers"""
    
    headers = {
        'X-ELS-APIKey': scopus_api_key,
        'Accept': 'application/json'
    }
    
    try:
        # Extract key terms from title
        title_words = re.findall(r'\b[a-zA-Z]{4,}\b', title.lower())
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        key_words = [word for word in title_words if word not in stop_words][:3]
        
        if not key_words:
            return []
        
        # Search by key terms
        search_terms = ' AND '.join([f'TITLE-ABS-KEY("{word}")' for word in key_words])
        
        response = requests.get(
            "https://api.elsevier.com/content/search/scopus",
            headers=headers,
            params={
                'query': search_terms,
                'count': max_results,
                'sort': 'relevancy',
                'field': 'dc:title,prism:doi'
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        papers = data.get('search-results', {}).get('entry', [])
        
        if not isinstance(papers, list):
            papers = [papers] if papers else []
        
        # Process papers
        related_papers = []
        for paper in papers:
            paper_doi = paper.get('prism:doi', '')
            paper_title = paper.get('dc:title', '')
            
            if paper_doi and paper_title:
                related_papers.append({'doi': paper_doi, 'title': paper_title})
        
        return related_papers
        
    except Exception as e:
        print(f"    Error searching by title: {e}")
        return []

def filter_papers_by_keywords(papers: List[Dict], keywords: List[str]) -> List[Dict]:
    """Filter papers by keywords in title"""
    if not keywords:
        return papers
    
    filtered_papers = []
    keywords_lower = [kw.lower() for kw in keywords]
    
    for paper in papers:
        title = paper.get('title', '').lower()
        if any(keyword in title for keyword in keywords_lower):
            filtered_papers.append(paper)
    
    return filtered_papers

def get_paper_text_from_scopus(doi: str, scopus_api_key: str) -> str:
    """Get paper abstract from Scopus"""
    
    headers = {
        'X-ELS-APIKey': scopus_api_key,
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get(
            "https://api.elsevier.com/content/search/scopus",
            headers=headers,
            params={
                'query': f'DOI("{doi}")',
                'count': 1,
                'field': 'dc:title,dc:description,dc:creator'
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        entries = data.get('search-results', {}).get('entry', [])
        if not entries:
            return ""
        
        paper = entries[0]
        text_parts = []
        
        title = paper.get('dc:title', '')
        if title:
            text_parts.append(f"Title: {title}")
        
        abstract = paper.get('dc:description', '')
        if abstract:
            text_parts.append(f"Abstract: {abstract}")
        
        return "\n\n".join(text_parts)
        
    except:
        return ""

def main():
    parser = argparse.ArgumentParser(description='Simple reference-based species extraction')
    
    parser.add_argument('--seed-paper', '-s', type=str, required=True, help='Seed PDF paper path')
    parser.add_argument('--output', '-o', type=str, required=True, help='Output CSV file')
    parser.add_argument('--claude-key', '-ck', type=str, required=True, help='Claude API key')
    parser.add_argument('--scopus-key', '-sk', type=str, required=True, help='Scopus API key')
    parser.add_argument('--max-papers', '-mp', type=int, default=20, help='Max papers to process')
    parser.add_argument('--max-depth', '-md', type=int, default=2, help='Max reference depth (1=refs, 2=refs of refs)')
    parser.add_argument('--keywords', '-kw', type=str, default='', help='Keywords to filter references (comma-separated)')
    
    args = parser.parse_args()
    
    # Parse keywords
    keywords = [kw.strip() for kw in args.keywords.split(',') if kw.strip()] if args.keywords else []
    
    print(f"🔬 Simple Reference-Based Species Extraction")
    print(f"📄 Seed paper: {args.seed_paper}")
    print(f"📤 Output: {args.output}")
    print(f"📊 Max papers: {args.max_papers}")
    print(f"📏 Max depth: {args.max_depth}")
    if keywords:
        print(f"🔍 Keywords filter: {', '.join(keywords)}")
    print("=" * 50)
    
    all_species_data = []
    processed_dois = set()
    papers_to_process = []
    
    # Process seed paper
    print(f"📄 Processing seed paper...")
    seed_text = extract_pdf_text(args.seed_paper)
    if not seed_text:
        print("❌ Could not extract text from seed paper")
        return
    
    # Extract DOI and title
    doi_match = re.search(r'(?:doi:?\s*|DOI:?\s*)([10]\.\d+/[^\s\]\),;]+)', seed_text, re.IGNORECASE)
    seed_doi = doi_match.group(1) if doi_match else "SEED_PAPER"
    
    lines = seed_text.split('\n')
    seed_title = ""
    for line in lines[:15]:
        line = line.strip()
        if 20 <= len(line) <= 200 and not any(x in line.lower() for x in ['doi:', 'page', 'journal', 'research article']):
            seed_title = line
            break
    if not seed_title:
        seed_title = "Seed Paper"
    
    print(f"✅ Extracted seed paper text ({len(seed_text)} chars)")
    print(f"📍 DOI: {seed_doi}")
    print(f"📝 Title: {seed_title}")
    
    # Add seed paper to processing list
    papers_to_process.append({
        'doi': seed_doi,
        'title': seed_title,
        'text': seed_text,
        'distance': 0
    })
    
    papers_processed = 0
    
    # Process papers queue (seed + references)
    while papers_to_process and papers_processed < args.max_papers:
        current_paper = papers_to_process.pop(0)
        current_doi = current_paper['doi']
        current_distance = current_paper['distance']
        
        # Skip if already processed
        if current_doi in processed_dois:
            continue
            
        processed_dois.add(current_doi)
        papers_processed += 1
        
        print(f"📄 Processing paper {papers_processed}/{args.max_papers} (distance {current_distance}): {current_paper['title'][:50]}...")
        
        # Extract species from current paper
        species_data = extract_species_from_text(
            current_paper['text'], 
            current_doi, 
            current_paper['title'], 
            current_distance, 
            args.claude_key
        )
        all_species_data.extend(species_data)
        print(f"✅ Found {len(species_data)} species")
        
        # Get references if we haven't reached max depth
        if current_distance < args.max_depth:
            print(f"🔍 Getting references from distance {current_distance} paper...")
            
            references = []
            
            # Try to get references using DOI
            if current_doi != "SEED_PAPER":
                references = get_paper_references(current_doi, args.scopus_key)
            
            # If no references found via DOI, try title search
            if not references:
                print(f"⚠️  No references via DOI, trying title search...")
                related_papers = search_papers_by_title(current_paper['title'], args.scopus_key, 15)
                references = related_papers
            
            print(f"✅ Found {len(references)} potential references")
            
            # Filter by keywords if provided
            if keywords and references:
                filtered_refs = filter_papers_by_keywords(references, keywords)
                print(f"🔍 Filtered to {len(filtered_refs)} papers matching keywords: {', '.join(keywords)}")
                references = filtered_refs
            
            # Add references to processing queue
            refs_added = 0
            for ref in references:
                ref_doi = ref['doi']
                ref_title = ref['title']
                
                # Skip if already processed or in queue
                if ref_doi not in processed_dois and not any(p['doi'] == ref_doi for p in papers_to_process):
                    # Get reference text
                    ref_text = get_paper_text_from_scopus(ref_doi, args.scopus_key)
                    if ref_text:
                        papers_to_process.append({
                            'doi': ref_doi,
                            'title': ref_title,
                            'text': ref_text,
                            'distance': current_distance + 1
                        })
                        refs_added += 1
                        print(f"📚 Added to queue (distance {current_distance + 1}): {ref_title[:50]}...")
                        
                        # Stop adding if we have enough papers queued
                        if len(papers_to_process) + papers_processed >= args.max_papers:
                            break
                    else:
                        print(f"⚠️  No text available for: {ref_title[:50]}...")
            
            print(f"✅ Added {refs_added} new references to queue")
        
        # Rate limiting
        if papers_processed < args.max_papers and papers_to_process:
            print(f"⏳ Waiting 3 seconds before next paper...")
            time.sleep(3)
    
    # Save results
    if all_species_data:
        df = pd.DataFrame(all_species_data)
        
        # Ensure column order
        columns = ['doi', 'species', 'abundance_or_biomass', 'number', 'location', 'distance_from_seed', 'title']
        for col in columns:
            if col not in df.columns:
                df[col] = "UNSPECIFIED"
        
        df = df[columns]
        df.to_csv(args.output, index=False, quoting=csv.QUOTE_ALL, encoding='utf-8')
        
        print(f"✅ Saved {len(df)} species entries to {args.output}")
        print(f"📊 Unique species: {df['species'].nunique()}")
        
        # Show distance breakdown
        distance_counts = df['distance_from_seed'].value_counts().sort_index()
        for dist, count in distance_counts.items():
            print(f"  Distance {dist}: {count} entries")
            
        print(f"📊 Total papers processed: {papers_processed}")
    else:
        print("⚠️  No species data extracted")

if __name__ == "__main__":
    main()
