# 1. INSTALL DEPENDENCIES
!pip install pymupdf polars xlsxwriter -q

import fitz
import pandas as pd
import re
import time
from google.colab import files

# --- 1. UNIVERSAL REGEX ---
RE_RULE_ID = re.compile(r'^(\d+(?:\.\d+)+)')
RE_TOC_SEARCH = re.compile(r'^(\d+(?:\.\d+)+)\s+(.*?)\s+(\d+)$')

KEYWORDS = {
    "Profile Applicability": "Level",
    "Description": "Description",
    "Rationale": "Rationale",
    "Impact": "Impact",
    "Audit": "Audit",
    "Remediation": "Remediation",
    "Default Value": "Default Value",
    "References": "References"
}

# --- 2. CORE ENGINE: ATOMIC STATE-MACHINE ---
def predator_engine_v12(pdf_path):
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    
    print(f"[*] Mapping Table of Contents...")
    master_toc_ids = []
    for i in range(min(60, total_pages)):
        text = doc[i].get_text("text")
        for line in text.split('\n'):
            clean_line = line.strip()
            if RE_TOC_SEARCH.search(clean_line):
                match = RE_TOC_SEARCH.search(clean_line)
                master_toc_ids.append(match.group(1))
    
    master_toc_ids = sorted(list(set(master_toc_ids)), key=lambda x: [int(i) for i in x.split('.')])
    
    if not master_toc_ids:
        print("[!] Gagal memetakan ToC.")
    
    print(f"[*] Streaming {total_pages} pages into Atomic State-Machine...")
    
    all_results = []
    current_rule = None
    active_section = "Description"
    
    for p in range(total_pages):
        blocks = doc[p].get_text("blocks")
        blocks.sort(key=lambda b: b[1])
        
        for b in blocks:
            line_text = b[4].replace('\n', ' ').strip()
            if not line_text: continue
            
            id_match = RE_RULE_ID.match(line_text)
            if id_match:
                rid = id_match.group(1)
                if rid in master_toc_ids:
                    if current_rule:
                        all_results.append(current_rule)
                    
                    title_clean = line_text.replace(rid, "", 1).strip()
                    current_rule = {
                        "Rule ID": rid, "Title": title_clean,
                        "Level": "N/A", "Description": "", "Rationale": "",
                        "Impact": "", "Audit": "", "Remediation": "",
                        "Default Value": "", "References": ""
                    }
                    active_section = "Title"
                    continue

            if current_rule:
                found_keyword = False
                for k_text, k_map in KEYWORDS.items():
                    if k_text.lower() in line_text.lower()[:30]:
                        active_section = k_map
                        content = re.sub(f'.*?{k_text}:?', '', line_text, flags=re.IGNORECASE).strip()
                        if content:
                            current_rule[active_section] += " " + content
                        found_keyword = True
                        break
                
                if not found_keyword:
                    if ("Level 1" in line_text or "Level 2" in line_text) and active_section == "Title":
                        current_rule["Level"] = line_text
                    else:
                        if not re.search(r'Page \d+ of \d+', line_text, re.IGNORECASE):
                            current_rule[active_section] += " " + line_text

    if current_rule:
        all_results.append(current_rule)

    doc.close()
    return all_results

# --- 3. DEBUG & EXECUTION (FIXED EXPORT) ---
uploaded = files.upload()
for filename in uploaded.keys():
    t_start = time.time()
    raw_data = predator_engine_v12(filename)
    
    if raw_data:
        # DATA CLEANING & EXCEL SAFE-GUARD
        for r in raw_data:
            for k in r:
                if isinstance(r[k], str):
                    clean_str = " ".join(r[k].split()).strip()
                    # FIX 1: Potong max 32k karakter supaya Excel nggak muntah
                    r[k] = clean_str[:32000] 
        
        df = pd.DataFrame(raw_data)
        print(f"\n[+] SUCCESS! Berhasil ambil {len(df)} Rules.")
        print(f"[+] Speed: {time.time()-t_start:.2f} detik.")
        
        out_name = f"TITAN_V12_{filename.replace('.pdf', '.xlsx')}"
        
        # FIX 2: Matikan auto-URL xlsxwriter yang bikin error "NoneType replace"
        engine_options = {'options': {'strings_to_urls': False}}
        with pd.ExcelWriter(out_name, engine='xlsxwriter', engine_kwargs=engine_options) as writer:
            df.to_excel(writer, index=False)
        
        files.download(out_name)
    else:
        print("[!] Gagal total. Cek struktur PDF.")
