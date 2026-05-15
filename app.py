import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import re
import time
import io
import json
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# 1. ENHANCED CORE ENGINE: TITAN PRO 6.0 (OMNISCIENCE + MULTI-THREADING)
# =============================================================================

@dataclass
class ParseResult:
    rule_id: str
    title: str = ""
    level: str = ""
    priority: str = "Medium"  
    description: str = ""
    rationale: str = ""
    impact: str = ""
    audit: str = ""
    remediation: str = ""
    default_value: str = ""
    references: str = ""
    found_on_page: int = -1
    recovery_method: str = "exact"
    confidence: float = 1.0

class TitanOmniscienceBackend:
    def __init__(self):
        # REGEX ORISINAL (Tidak Diubah)
        self.RE_RULE_EXACT   = re.compile(r'^(\d+(?:\.\d+)+)\s+(.+)', re.IGNORECASE)
        self.RE_RULE_FUZZY   = re.compile(r'([lI1\d][\s\.\d]*\d)\s+(Ensure|Do\s+not|Review|Keep|Use)\s+', re.IGNORECASE)
        self.RE_RULE_HEADING = re.compile(r'^(\d+(?:\.\d+)+)\b')

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

    # --- UTILITIES ---
    def _get_parent_id(self, rule_id: str) -> str:
        parts = rule_id.split('.')
        return '.'.join(parts[:-1]) if len(parts) > 1 else "Root"

    def _get_priority(self, title: str, description: str) -> str:
        combined = (title + " " + description).lower()
        if any(x in combined for x in ["password", "credential", "private key", "encryption", "admin", "root"]): return "Critical"
        if any(x in combined for x in ["remote access", "ssh", "rdp", "firewall", "network", "access control"]): return "High"
        if any(x in combined for x in ["audit", "logging", "monitoring", "banner", "message"]): return "Medium"
        return "Low"

    def _clean_text(self, parts: List[str]) -> str:
        if not parts: return "N/A"
        joined = self.RE_NOISE.sub("", " ".join(parts))
        return " ".join(joined.split()).strip() or "N/A"

    def _extract_level(self, parts: List[str]) -> str:
        joined = " ".join(parts)
        m = self.RE_LEVEL.search(joined)
        return f"Level {m.group(1)}" if m else (joined.strip() or "N/A")

    def _sort_key(self, rule_id: str) -> list:
        try: return [int(p) for p in rule_id.split(".")]
        except ValueError: return [0]

    def _empty_rule(self) -> dict:
        return {"title": [], "level": [], "description": [], "rationale": [], "impact": [], "audit": [], "remediation": [], "default_value": [], "references": []}

    def _build_result(self, rule_id: str, data: dict, page: int, method: str, confidence: float) -> ParseResult:
        res = ParseResult(
            rule_id=rule_id, title=self._clean_text(data["title"]), level=self._extract_level(data["level"]),
            description=self._clean_text(data["description"]), rationale=self._clean_text(data["rationale"]),
            impact=self._clean_text(data["impact"]), audit=self._clean_text(data["audit"]),
            remediation=self._clean_text(data["remediation"]), default_value=self._clean_text(data["default_value"]),
            references=self._clean_text(data["references"]), found_on_page=page, recovery_method=method, confidence=confidence
        )
        res.priority = self._get_priority(res.title, res.description)
        return res

    # --- MULTI-PASS COMPONENTS ---
    def _try_detect_rule(self, line: str, mode: str) -> Optional[Tuple[str, str]]:
        line = line.strip()
        if not line: return None
        if mode == "exact":
            m = self.RE_RULE_EXACT.match(line)
            if m: return m.group(1), m.group(2).strip()
        elif mode == "fuzzy":
            norm = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', line)
            norm = re.sub(r'^[lIi]\.', '1.', norm)
            m = self.RE_RULE_EXACT.match(norm)
            if m: return m.group(1), m.group(2).strip()
        elif mode == "heading":
            m = self.RE_RULE_HEADING.match(line)
            if m and "." in m.group(1): return m.group(1), line[m.end():].strip()
        return None

    def _parse_rules_from_text(self, text: str, target_ids: Set[str], mode: str = "exact") -> Dict[str, dict]:
        rules = {}
        current_id, current_section = None, "title"
        content = self._empty_rule()

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped: continue

            detected = self._try_detect_rule(stripped, mode)
            if detected:
                rid, title = detected
                if not target_ids or rid in target_ids:
                    if current_id and (not target_ids or current_id in target_ids):
                        rules[current_id] = content
                    current_id, current_section = rid, "title"
                    content = self._empty_rule()
                    content["title"].append(title)
                    continue

            if current_id is None: continue

            if current_section == "title":
                m_inline = re.search(r'(.*?)\s*(Profile\s+Applicability|Level\s*[123])\s*:?\s*(.*)', stripped, re.IGNORECASE)
                if m_inline and re.search(r'\((?:Automated|Manual)\)$', m_inline.group(1).strip(), re.IGNORECASE):
                    content["title"].append(m_inline.group(1).strip())
                    current_section = "level"
                    content[current_section].append((m_inline.group(2) + " " + m_inline.group(3)).strip())
                    continue

            s_match = self.RE_SECTION.match(stripped)
            if s_match:
                raw_key = s_match.group(1).lower()
                for k, v in self.SECTION_MAP.items():
                    if raw_key.startswith(k): current_section = v; break
                rem = self.RE_SECTION.sub("", stripped).strip()
                if rem: content[current_section].append(rem)
            else:
                content[current_section].append(stripped)

        if current_id and (not target_ids or current_id in target_ids):
            rules[current_id] = content
        return rules

    def _page_range_for_gap(self, gap_id: str, toc: Dict[str, int], total_pages: int) -> Tuple[int, int]:
        all_ids = sorted(toc.keys(), key=self._sort_key)
        try: idx = all_ids.index(gap_id)
        except ValueError: return 0, total_pages - 1

        prev_pg, next_pg = 1, total_pages
        for i in range(idx - 1, -1, -1):
            if all_ids[i] in toc and toc[all_ids[i]] > 0: prev_pg = toc[all_ids[i]]; break
        for i in range(idx + 1, len(all_ids)):
            if all_ids[i] in toc and toc[all_ids[i]] > 0: next_pg = toc[all_ids[i]]; break
        return max(0, prev_pg - 3), min(total_pages - 1, next_pg + 1)

    def _qc_sweep(self, pages_text: List[str], found: Dict[str, ParseResult]) -> Tuple[Dict[str, ParseResult], List[str]]:
        jumps = []
        sorted_ids = sorted(found.keys(), key=self._sort_key)
        for i in range(len(sorted_ids) - 1):
            curr, nxt = sorted_ids[i].split('.'), sorted_ids[i+1].split('.')
            if len(curr) == len(nxt) and curr[:-1] == nxt[:-1]:
                curr_last, nxt_last = int(curr[-1]), int(nxt[-1])
                if nxt_last > curr_last + 1:
                    for missing in range(curr_last + 1, nxt_last):
                        jumps.append('.'.join(curr[:-1] + [str(missing)]))
                        
        verified_skipped = []
        rescued = {}

        if jumps:
            for gap_id in jumps:
                temp_list = sorted(list(found.keys()) + [gap_id], key=self._sort_key)
                idx = temp_list.index(gap_id)
                start_pg = found[temp_list[idx-1]].found_on_page if idx > 0 else 0
                end_pg = found[temp_list[idx+1]].found_on_page if idx < len(temp_list)-1 else len(pages_text)-1

                is_in_pdf = False
                for pg in range(max(0, start_pg - 2), min(len(pages_text), end_pg + 2)):
                    if re.search(rf'^{gap_id}\s+[A-Z]', pages_text[pg], re.MULTILINE):
                        raw = self._parse_rules_from_text(pages_text[pg], {gap_id}, mode="exact")
                        if gap_id in raw:
                            rescued[gap_id] = self._build_result(gap_id, raw[gap_id], pg+1, "qc_rescue", 0.95)
                            is_in_pdf = True
                            break
                if not is_in_pdf: verified_skipped.append(gap_id)

        found.update(rescued)
        return found, verified_skipped

    def _cleanse_bleeding(self, found_dict: Dict[str, ParseResult]) -> Dict[str, ParseResult]:
        all_ids = sorted(found_dict.keys(), key=self._sort_key)
        for i in range(len(all_ids) - 1):
            curr_rule, next_id = found_dict[all_ids[i]], all_ids[i+1]
            bleed_pattern = re.compile(rf'(?:\s|^){re.escape(next_id)}\s+(?:Ensure|Do\s+not|Review|Keep|Use|Configure|Turn\s+off|Disable|Enable|Allow|Deny|Restrict|Set|Require|Prevent|Limit|Block|Force|Audit)\b', re.IGNORECASE)
            
            for field in ['references', 'default_value', 'remediation', 'audit', 'impact', 'rationale', 'description', 'level', 'title']:
                val = getattr(curr_rule, field)
                if val and next_id in val:
                    m = bleed_pattern.search(val)
                    if m:
                        setattr(curr_rule, field, val[:m.start()].strip() or "N/A")
                        break 
        return found_dict

    # --- MASTER ENGINE: MULTI-PASS VALIDATION ---
    def process_pdf(self, pdf_bytes: bytes) -> Tuple[List[dict], dict]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # ⚡ MULTI-THREADING: Baca teks dokumen secara paralel
        with ThreadPoolExecutor() as exe:
            pages_text = list(exe.map(lambda page: self.RE_NOISE.sub("", page.get_text("text")), doc))
        
        # Ground Truth
        toc_pages, master_ids = {}, []
        in_app = False
        for pg_idx in range(min(100, len(pages_text))):
            for line in pages_text[pg_idx].split("\n"):
                m_toc = self.RE_TOC.match(line.strip())
                if m_toc: toc_pages[m_toc.group(1)] = int(m_toc.group(2))
                
        for pg_idx in range(len(pages_text)):
            for line in pages_text[pg_idx].split("\n"):
                clean_line = line.strip()
                if self.RE_APPENDIX_START.search(clean_line): in_app = True
                if in_app and self.RE_APPENDIX_STOP.search(clean_line): in_app = False
                if in_app:
                    m_rid = re.match(r'^(\d+(?:\.\d+)+)', clean_line)
                    if m_rid: master_ids.append(m_rid.group(1))

        master_ids = list(dict.fromkeys(master_ids))
        if not master_ids: master_ids = sorted(list(toc_pages.keys()), key=self._sort_key)
        for rid in master_ids: 
            if rid not in toc_pages: toc_pages[rid] = 0
            
        valid_ids = set(toc_pages.keys())

        # ⚡ PASS 1: GLOBAL EXACT
        full_doc_text = "\n".join(pages_text)
        raw_pass1 = self._parse_rules_from_text(full_doc_text, valid_ids, mode="exact")
        found = {rid: self._build_result(rid, data, toc_pages.get(rid, -1), "exact", 1.0) for rid, data in raw_pass1.items()}

        # ⚡ PASS 2: LOCAL RESCAN (Fuzzy & Heading)
        gaps = sorted([rid for rid in toc_pages if rid not in found], key=self._sort_key)
        if gaps:
            for gap_id in gaps:
                start_pg, end_pg = self._page_range_for_gap(gap_id, toc_pages, len(pages_text))
                for mode in ["fuzzy", "heading"]:
                    for pg in range(start_pg, end_pg + 1):
                        raw_pass2 = self._parse_rules_from_text(pages_text[pg], {gap_id}, mode=mode)
                        if gap_id in raw_pass2:
                            found[gap_id] = self._build_result(gap_id, raw_pass2[gap_id], pg + 1, f"local_{mode}", 0.8)
                            break
                    if gap_id in found: break

        # ⚡ PASS 3: 360 BACKWARDS SCAN
        remaining_gaps = [rid for rid in toc_pages if rid not in found]
        if remaining_gaps:
            for pg_idx in range(len(pages_text) - 1, -1, -1):
                if not remaining_gaps: break
                for mode in ["exact", "fuzzy", "heading"]:
                    raw_pass3 = self._parse_rules_from_text(pages_text[pg_idx], set(remaining_gaps), mode=mode)
                    for gap_id, data in raw_pass3.items():
                        if gap_id not in found:
                            found[gap_id] = self._build_result(gap_id, data, pg_idx + 1, f"360_backwards_{mode}", 0.6)
                            remaining_gaps.remove(gap_id)

        # ⚡ PASS 4: QA/QC SWEEPER & BLEED CLEANSING
        found, verified_skipped = self._qc_sweep(pages_text, found)
        found = self._cleanse_bleeding(found)

        parent_ids = {self._get_parent_id(rid) for rid in valid_ids}
        final_found = {k: v for k, v in found.items() if (v.audit != "N/A" or v.remediation != "N/A" or v.description != "N/A")}

        report = {
            "status": "OMNISCIENCE VALIDATION COMPLETED",
            "toc_count": len(toc_pages), 
            "found_count": len(final_found),
            "verified_skipped_by_cis": verified_skipped,
            "unrecovered_rules": [rid for rid in toc_pages if rid not in final_found and rid not in verified_skipped and rid not in parent_ids]
        }

        doc.close()
        records = [asdict(f) for rid, f in sorted(final_found.items(), key=lambda x: self._sort_key(x[0]))]
        
        # Inject Parent ID untuk Dataframe UI
        for r in records: r["parent_id"] = self._get_parent_id(r["rule_id"])
            
        return records, report

# =============================================================================
# ⚡ PERFORMA UPGRADE: STREAMLIT MEMORY CACHING
# =============================================================================
@st.cache_data(show_spinner=False)
def execute_titan_cacheable(file_bytes: bytes, filename: str):
    engine = TitanOmniscienceBackend()
    return engine.process_pdf(file_bytes)

# =============================================================================
# 2. UI FRAMEWORK & AESTHETIC DASHBOARD
# =============================================================================

st.set_page_config(page_title="TITAN PRO 6.0", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")

if "theme" not in st.session_state: st.session_state.theme = "Dark"
if "db" not in st.session_state: st.session_state.db = {}
if "logs" not in st.session_state: st.session_state.logs = []

def toggle_theme():
    st.session_state.theme = "Light" if st.session_state.theme == "Dark" else "Dark"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Fira+Code&display=swap');
    :root {{
        --primary: {"#00E5FF" if st.session_state.theme == "Dark" else "#2563EB"};
        --secondary: {"#7000FF" if st.session_state.theme == "Dark" else "#4F46E5"};
        --bg: {"#0A0F1C" if st.session_state.theme == "Dark" else "#F3F4F6"};
        --card-bg: {"rgba(16, 24, 39, 0.65)" if st.session_state.theme == "Dark" else "rgba(255, 255, 255, 0.9)"};
        --text: {"#E2E8F0" if st.session_state.theme == "Dark" else "#1E293B"};
        --border: {"rgba(0, 229, 255, 0.2)" if st.session_state.theme == "Dark" else "rgba(37, 99, 235, 0.2)"};
    }}
    .stApp {{ background-color: var(--bg); color: var(--text); font-family: 'Rajdhani', sans-serif; background-image: {"radial-gradient(circle at 50% 0%, #111827 0%, #0A0F1C 100%)" if st.session_state.theme == "Dark" else "none"}; }}
    [data-testid="stMetricContainer"] {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; backdrop-filter: blur(12px); box-shadow: 0 8px 32px rgba(0,0,0,0.15); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
    [data-testid="stMetricContainer"]:hover {{ border-color: var(--primary); box-shadow: 0 0 20px rgba(0, 229, 255, 0.2); transform: translateY(-2px); }}
    h1, h2, h3 {{ font-family: 'Rajdhani', sans-serif; letter-spacing: 1px; }}
    [data-testid="stSidebar"] {{ background-color: {"rgba(11, 15, 25, 0.95)" if st.session_state.theme == "Dark" else "#FFFFFF"}; border-right: 1px solid var(--border); }}
    .stButton>button {{ border-radius: 8px; transition: all 0.2s; font-weight: 600; letter-spacing: 0.5px; }}
    [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: var(--primary);'>🛡️ TITAN CORE 6.0</h2>", unsafe_allow_html=True)
    nav = st.sidebar.radio("COMMAND CENTER", ["DASHBOARD", "UPLOAD CENTER", "RULES VIEWER", "EXPORT CENTER", "LOGS"], label_visibility="collapsed")
    st.markdown("---")
    st.button(f"{'☀️ LIGHT' if st.session_state.theme == 'Dark' else '🌙 DARK'} MODE", on_click=toggle_theme, use_container_width=True)

# =============================================================================
# 3. PAGES LOGIC
# =============================================================================

if nav == "DASHBOARD":
    st.title("📊 AUDIT INTELLIGENCE DASHBOARD")
    if not st.session_state.db:
        st.info("⚡ System Standby. Awaiting data ingestion at Upload Center.")
    else:
        total_rules = sum(len(f['data']) for f in st.session_state.db.values())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("LOADED FILES", len(st.session_state.db))
        c2.metric("RULES EXTRACTED", f"{total_rules:,}")
        c3.metric("INTEGRITY", "HIGH", delta="Omniscience Active", delta_color="normal")
        c4.metric("ENGINE STATUS", "MULTI-THREADED")
        
        st.markdown("<br>", unsafe_allow_html=True)
        col_left, col_right = st.columns(2)
        
        all_data = []
        for f in st.session_state.db.values(): all_data.extend(f['data'])
        combined_df = pd.DataFrame(all_data)
        
        with col_left:
            st.markdown("#### Security Priority Distribution")
            fig_prio = px.pie(combined_df, names='priority', color='priority', hole=0.4,
                             color_discrete_map={'Critical':'#FF2A2A', 'High':'#FF9500', 'Medium':'#FFCC00', 'Low':'#00FF88'})
            fig_prio.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_family="Rajdhani", font_color="var(--text)")
            st.plotly_chart(fig_prio, use_container_width=True)
            
        with col_right:
            st.markdown("#### Extraction Confidence Level")
            fig_conf = px.histogram(combined_df, x='confidence', template="plotly_dark" if st.session_state.theme=="Dark" else "plotly",
                                  color_discrete_sequence=['var(--primary)'])
            fig_conf.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_family="Rajdhani")
            st.plotly_chart(fig_conf, use_container_width=True)

elif nav == "UPLOAD CENTER":
    st.title("☁️ SECURE INGESTION")
    st.markdown("Multi-pass Engine akan membedah PDF melalui 4 tahap validasi (Exact, Local, 360 Backwards, QA/QC).")
    files = st.file_uploader("Drop files here", type="pdf", accept_multiple_files=True)
    
    if files and st.button("🚀 EXECUTE MULTI-PASS VALIDATION", type="primary", use_container_width=True):
        for f in files:
            with st.status(f"⚡ Ingesting {f.name}...", expanded=True) as status:
                st.write("1️⃣ Multi-threaded Text Extraction...")
                st.write("2️⃣ Pass 1: Global Exact Regex Check...")
                st.write("3️⃣ Pass 2: Local Fuzzy Rescan...")
                st.write("4️⃣ Pass 3: 360° Backwards Audit...")
                st.write("5️⃣ Pass 4: QA/QC Sequence Verifier...")
                
                res, report = execute_titan_cacheable(f.read(), f.name)
                
                st.session_state.db[f.name] = {"data": res, "report": report}
                st.session_state.logs.append(f"[SUCCESS] {f.name} parsed. Multi-pass Validated: {len(res)} rules.")
                status.update(label=f"✅ {f.name} Processed ({len(res)} Rules)", state="complete", expanded=False)
                
        st.toast("Multi-pass Validation Selesai!", icon="✅")
        time.sleep(0.5)
        st.rerun()

elif nav == "RULES VIEWER":
    st.title("🛡️ RULE EXPLORER")
    if not st.session_state.db: 
        st.warning("⚠️ Memori kosong. Upload file terlebih dahulu.")
    else:
        target = st.selectbox("Select Target Database", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        
        search = st.text_input("🔍 Quick Search (ID, Title, Priority...)", placeholder="Ketik keyword di sini...")
        if search: 
            df = df[df.apply(lambda r: search.lower() in str(r.values).lower(), axis=1)]
        
        st.markdown(f"**Menampilkan {len(df)} rules terverifikasi.**")
        st.dataframe(
            df[["rule_id", "parent_id", "priority", "title", "level", "recovery_method", "confidence"]], 
            use_container_width=True, 
            height=600,
            hide_index=True,
            column_config={
                "priority": st.column_config.TextColumn("Priority", help="Security Impact"),
                "recovery_method": st.column_config.TextColumn("Recovery Pass", help="Tahap dimana rule ini ditemukan")
            }
        )

elif nav == "EXPORT CENTER":
    st.title("💾 MULTI-FORMAT EXPORT")
    if not st.session_state.db: 
        st.warning("⚠️ Tidak ada data untuk diekspor.")
    else:
        target = st.selectbox("Pilih Database untuk Diekspor", list(st.session_state.db.keys()))
        df = pd.DataFrame(st.session_state.db[target]["data"])
        
        for col in df.columns: df[col] = df[col].apply(lambda x: str(x)[:32000] if isinstance(x, str) else x)
        
        # Susun ulang kolom biar rapi pas di Excel
        col_order = ["rule_id", "parent_id", "title", "level", "priority", "description", "rationale", "impact", "audit", "remediation", "default_value", "references", "found_on_page", "recovery_method", "confidence"]
        df = df[[c for c in col_order if c in df.columns]]

        st.markdown("<br><br>### 📥 Select Output Format", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        
        with c1:
            buffer_xlsx = io.BytesIO()
            with pd.ExcelWriter(buffer_xlsx, engine='xlsxwriter', engine_kwargs={'options': {'strings_to_urls': False}}) as writer:
                df.to_excel(writer, index=False, sheet_name='Validated_Rules')
            st.download_button("📊 EXCEL WORKBOOK (.xlsx)", buffer_xlsx.getvalue(), f"Titan_{target}.xlsx", use_container_width=True)
            
        with c2:
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button("📄 RAW CSV (.csv)", csv_data, f"Titan_{target}.csv", "text/csv", use_container_width=True)
            
        with c3:
            json_data = df.to_json(orient='records', indent=4)
            st.download_button("📦 JSON PAYLOAD (.json)", json_data, f"Titan_{target}.json", "application/json", use_container_width=True)

elif nav == "LOGS":
    st.title("💻 SYSTEM CONSOLE")
    log_str = "\n".join(st.session_state.logs[::-1]) if st.session_state.logs else "Awaiting tasks...\nEngine idling at 0% load."
    st.code(log_str, language="bash")

st.markdown('<div style="position: fixed; bottom: 10px; right: 20px; opacity: 0.3; font-family: \'Fira Code\', monospace; font-size: 11px;">TITAN PRO 6.0 // OMNISCIENCE MULTI-PASS VALIDATED</div>', unsafe_allow_html=True)
