import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import time
import io
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# 1. CORE ENGINE: TITAN PRO 5.2.1 (DEEP-SEQUENCE & ANTI-BLEED)
# =============================================================================

@dataclass
class ParseResult:
    rule_id: str
    title: str = ""
    level: str = ""
    description: str = ""
    rationale: str = ""
    impact: str = ""
    audit: str = ""
    remediation: str = ""
    default_value: str = ""
    references: str = ""
    found_on_page: int = -1
    recovery_method: str = "exact"

class TitanBackend:
    def __init__(self):
        self.RE_RULE_EXACT = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
        self.RE_SECTION = re.compile(
            r'^(Profile\s+Applicability|Level\s*[123]|Description|Rationale(?:\s+Statement)?'
            r'|Impact(?:\s+Statement)?|Audit(?:\s+Procedure)?'
            r'|Remediation(?:\s+Procedure)?|Default\s+Value|References):?\s*', re.IGNORECASE)
        self.RE_TOC = re.compile(r'^(\d+(?:\.\d+)+).*?(?:\.+)\s*(\d+)\s*$')
        self.RE_NOISE = re.compile(r'(Page\s+\d+|Internal\s+Only[^\n]*|P\s+a\s+g\s+e\s*\|\s*\d+)', re.IGNORECASE)
        self.RE_LEVEL = re.compile(r'Level\s*(\d+)', re.IGNORECASE)
        self.RE_APPENDIX_START = re.compile(r'^(?:Appendix:\s*)?(?:Summary\s+Table|Recommendation\s+Summary|CIS\s+Controls\s+v\d+\s+IG\s+\d+\s+Mapped\s+Recommendations)', re.IGNORECASE)
        self.RE_APPENDIX_STOP = re.compile(r'^(?:Appendix:\s*)?Change History', re.IGNORECASE)
        
        self.SECTION_MAP = {
            "profile applicability": "level", "level 1": "level", "level 2": "level", "level 3": "level",
            "description": "description", "rationale": "rationale", "impact": "impact",
            "audit": "audit", "remediation": "remediation", "default value": "default_value", "references": "references"
        }

    def _clean_text(self, parts: List[str]) -> str:
        joined = self.RE_NOISE.sub("", " ".join(parts))
        return " ".join(joined.split()).strip() or "N/A"

    def _extract_level(self, parts: List[str]) -> str:
        joined = " ".join(parts)
        m = self.RE_LEVEL.search(joined)
        return f"Level {m.group(1)}" if m else (joined.strip() or "N/A")

    def _sort_key(self, rule_id: str) -> list:
        try: return [int(p) for p in rule_id.split(".")]
        except: return [0]

    def get_deep_recursive_jumps(self, ids: List[str]) -> List[str]:
        from collections import defaultdict
        tree = defaultdict(list)
        for rid in ids:
            parts = rid.split('.')
            if len(parts) < 2: continue
            parent = ".".join(parts[:-1])
            try: tree[parent].append(int(parts[-1]))
            except: continue
        jumps = []
        for parent, children in tree.items():
            children.sort()
            for i in range(len(children) - 1):
                curr, nxt = children[i], children[i+1]
                if nxt > curr + 1:
                    for m in range(curr + 1, nxt): jumps.append(f"{parent}.{m}")
        return jumps

    def process_pdf(self, pdf_bytes: bytes) -> Tuple[List[dict], dict]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        cache = [self.RE_NOISE.sub("", page.get_text("text")) for page in doc]
        
        toc_pages = {}
        master_ids = []
        in_app = False
        for pg in cache:
            for line in pg.split("\n"):
                line = line.strip()
                m_toc = self.RE_TOC.match(line)
                if m_toc: toc_pages[m_toc.group(1)] = int(m_toc.group(2))
                if self.RE_APPENDIX_START.search(line): in_app = True
                if in_app and self.RE_APPENDIX_STOP.search(line): in_app = False
                if in_app:
                    m_rid = re.match(r'^(\d+(?:\.\d+)+)', line)
                    if m_rid: master_ids.append(m_rid.group(1))

        master_ids = list(dict.fromkeys(master_ids))
        if not master_ids: master_ids = sorted(list(toc_pages.keys()), key=self._sort_key)

        final_rules = {}
        full_content = "\n".join(cache)
        current_id, current_sec = None, "title"
        tmp = {k: [] for k in ["title", "level", "description", "rationale", "impact", "audit", "remediation", "default_value", "references"]}

        for line in full_content.split("\n"):
            line = line.strip()
            m_rule = self.RE_RULE_EXACT.match(line)
            if m_rule and m_rule.group(1) in master_ids:
                if current_id:
                    final_rules[current_id] = ParseResult(current_id, **{k: (self._extract_level(v) if k=="level" else self._clean_text(v)) for k,v in tmp.items()}, found_on_page=toc_pages.get(current_id, -1))
                current_id, current_sec = m_rule.group(1), "title"
                tmp = {k: [] for k in tmp.keys()}; tmp["title"] = [m_rule.group(2)]
                continue
            if not current_id: continue
            m_sec = self.RE_SECTION.match(line)
            if m_sec:
                for k,v in self.SECTION_MAP.items():
                    if m_sec.group(1).lower().startswith(k): current_sec = v; break
                rem = self.RE_SECTION.sub("", line).strip()
                if rem: tmp[current_sec].append(rem)
            else: tmp[current_sec].append(line)

        if current_id:
            final_rules[current_id] = ParseResult(current_id, **{k: (self._extract_level(v) if k=="level" else self._clean_text(v)) for k,v in tmp.items()}, found_on_page=toc_pages.get(current_id, -1))

        jumps = self.get_deep_recursive_jumps(list(final_rules.keys()))
        verified_skipped = []
        for gap_id in jumps:
            found_gap = False
            for pg_text in cache:
                if re.search(rf'^{re.escape(gap_id)}\s+', pg_text, re.MULTILINE):
                    found_gap = True; break
            if not found_gap: verified_skipped.append(gap_id)

        ids = sorted(final_rules.keys(), key=self._sort_key)
        for i in range(len(ids)-1):
            curr, nxt = final_rules[ids[i]], ids[i+1]
            p = re.compile(rf'(?:\s|^){re.escape(nxt)}\s+(?:Ensure|Do\s+not|Review|Keep|Use|Audit|Set|Configure)\b', re.IGNORECASE)
            for attr in ["references", "default_value", "audit", "remediation"]:
                val = getattr(curr, attr)
                m = p.search(val)
                if m: setattr(curr, attr, val[:m.start()].strip()); break

        doc.close()
        return [asdict(final_rules[rid]) for rid in ids], {"skipped": verified_skipped, "toc_count": len(master_ids)}

# =============================================================================
# 2. EXPERIMENTAL: MULTI-PLATFORM AUTO-REMEDIATION
# =============================================================================

def generate_remediation_script(rule_id, title, remediation_text, platform="Windows"):
    """Menerjemahkan teks remediasi menjadi Script Hardening (PS atau Bash)."""
    if platform == "Windows":
        script = [f"# TITAN AUTO-FIX (WINDOWS): Rule {rule_id}", f"# {title}\n"]
        reg_path = re.search(r'(HKLM\\|HKEY_LOCAL_MACHINE\\)([\w\\]+)', remediation_text, re.I)
        reg_value = re.search(r'set\s+([\w\s]+)\s+to\s+(\d+)', remediation_text, re.I)
        
        if reg_path and reg_value:
            path = reg_path.group(0).replace("HKEY_LOCAL_MACHINE", "HKLM")
            val_name, val_data = reg_value.group(1).strip(), reg_value.group(2).strip()
            script.append(f"$path = 'Registry::{path}'")
            script.append(f"if (!(Test-Path $path)) {{ New-Item -Path $path -Force }}")
            script.append(f"Set-ItemProperty -Path $path -Name '{val_name}' -Value {val_data} -Type DWord")
        else:
            script.append(f"# Manual check required for Windows logic.")
        return "\n".join(script)
    
    else: # Linux Platform
        script = [f"#!/bin/bash", f"# TITAN AUTO-FIX (LINUX): Rule {rule_id}", f"# {title}\n"]
        
        # Logic: Config File Modification (e.g., /etc/ssh/sshd_config)
        conf_file = re.search(r'(/etc/[\w/\._-]+)', remediation_text)
        param_set = re.search(r'set\s+([\w_-]+)\s+to\s+([\w-]+)', remediation_text, re.I)
        
        if conf_file and param_set:
            file_path = conf_file.group(0)
            param, value = param_set.group(1), param_set.group(2)
            script.append(f"FILE='{file_path}'")
            script.append(f"PARAM='{param}'")
            script.append(f"VALUE='{value}'")
            script.append(f"if grep -q \"^$PARAM\" \"$FILE\"; then")
            script.append(f"  sed -i \"s/^$PARAM.*/$PARAM $VALUE/\" \"$FILE\"")
            script.append(f"else")
            script.append(f"  echo \"$PARAM $VALUE\" >> \"$FILE\"")
            script.append(f"fi")
        elif "service" in remediation_text.lower() and "disable" in remediation_text.lower():
            svc = re.search(r'service\s+([\w-]+)', remediation_text, re.I)
            if svc: script.append(f"systemctl disable --now {svc.group(1)}")
        else:
            script.append(f"# Logic extraction failed. Refer to remediation text:")
            script.append(f"# {remediation_text[:150]}...")
        return "\n".join(script)

# =============================================================================
# 3. UI FRAMEWORK
# =============================================================================

st.set_page_config(page_title="Titan CIS Extractor", page_icon="🛡️", layout="wide")

if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "db" not in st.session_state: st.session_state.db = {}
if "logs" not in st.session_state: st.session_state.logs = []

def toggle_theme():
    st.session_state.theme = "Light" if st.session_state.theme == "Dark" else "Dark"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Fira+Code&display=swap');
    :root {{
        --primary: {"#00F0FF" if st.session_state.theme == "Dark" else "#1D4ED8"};
        --bg: {"#0B0F19" if st.session_state.theme == "Dark" else "#F9FAFB"};
        --card: {"rgba(17, 24, 39, 0.8)" if st.session_state.theme == "Dark" else "#FFFFFF"};
        --text: {"#E5E7EB" if st.session_state.theme == "Dark" else "#111827"};
    }}
    .stApp {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; }}
    [data-testid="stMetricContainer"], .cyber-card {{ background: var(--card); border: 1px solid var(--primary); border-radius: 10px; padding: 15px; }}
    .console {{ background: #050505; color: #00FF41; font-family: 'Fira Code', monospace; padding: 15px; border-radius: 5px; height: 250px; overflow-y: auto; font-size: 0.8rem; }}
    .titan-branding {{ position: fixed; bottom: 10px; right: 20px; opacity: 0.4; font-size: 11px; }}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 4. NAVIGATION
# =============================================================================

with st.sidebar:
    st.title("🛡️ TITAN CORE")
    nav = st.sidebar.radio("COMMAND CENTER", ["DASHBOARD", "UPLOAD CENTER", "RULES VIEWER", "INTEGRITY VALIDATOR", "LOGS & SETTINGS"])
    st.markdown("---")
    st.button(f"🌓 MODE: {st.session_state.theme.upper()}", on_click=toggle_theme, use_container_width=True)

if nav == "DASHBOARD":
    st.title("📊 ANALYTICS DASHBOARD")
    c1, c2, c3 = st.columns(3)
    total_rules = sum(len(f['data']) for f in st.session_state.db.values())
    c1.metric("LOADED FILES", len(st.session_state.db))
    c2.metric("TOTAL RULES", total_rules)
    c3.metric("INTEGRITY", "A+" if total_rules > 0 else "N/A")
    if st.session_state.db: st.bar_chart(pd.DataFrame({k: [len(v['data'])] for k,v in st.session_state.db.items()}).T)

elif nav == "UPLOAD CENTER":
    st.title("☁️ SECURE DATA INGESTION")
    files = st.file_uploader("Upload CIS Benchmark PDF", type="pdf", accept_multiple_files=True)
    if files and st.button("🚀 EXECUTE TITAN ENGINE", type="primary", use_container_width=True):
        engine = TitanBackend()
        for f in files:
            with st.spinner(f"Extracting {f.name}..."):
                res, report = engine.process_pdf(f.read())
                st.session_state.db[f.name] = {"data": res, "report": report}
                st.session_state.logs.append(f"SUCCESS: {f.name} - {len(res)} rules mapped.")
        st.rerun()

elif nav == "RULES VIEWER":
    st.title("🛡️ RULE EXPLORER")
    if not st.session_state.db: st.warning("Silakan upload file di Upload Center.")
    else:
        target = st.selectbox("Select Target", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        search = st.text_input("Filter Rules...")
        if search: df = df[df.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)]
        st.dataframe(df, use_container_width=True, height=400)
        
        st.markdown("### 🪄 AUTO-REMEDIATION")
        col_p, col_r = st.columns([1, 3])
        with col_p: platform = st.selectbox("Target OS", ["Windows", "Linux"])
        with col_r: selected_rid = st.selectbox("Pilih Rule ID", df["rule_id"].tolist())
        
        if selected_rid:
            row = df[df["rule_id"] == selected_rid].iloc[0]
            code = generate_remediation_script(row["rule_id"], row["title"], row["remediation"], platform)
            st.code(code, language="powershell" if platform=="Windows" else "bash")

elif nav == "INTEGRITY VALIDATOR":
    st.title("🔍 DEEP SEQUENCE AUDIT")
    if not st.session_state.db: st.warning("No Data.")
    else:
        for k, v in st.session_state.db.items():
            with st.expander(f"Report: {k}"):
                st.write(f"**Missing/Shadow IDs:** {v['report']['skipped']}")

elif nav == "LOGS & SETTINGS":
    st.title("💻 SYSTEM CONSOLE")
    log_str = "\n".join(st.session_state.logs[::-1])
    st.markdown(f'<div class="console">{log_str.replace("\n", "<br>")}</div>', unsafe_allow_html=True)
    if st.button("🚨 PURGE DATABASE"):
        st.session_state.db = {}; st.session_state.logs = []; st.rerun()

st.markdown('<div class="titan-branding">TITAN EXTRACTOR 5.2.1 | BY LUCKY PRADANA</div>', unsafe_allow_html=True)
