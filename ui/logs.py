import streamlit as st
import os
from datetime import datetime
from services.utils import MSK
from ui.shared import df_to_tsv

def render_logs(get_log_text, GLOBAL_LOG_QUEUE, _LOGS_DIR, log):
    st.markdown(
        '<div style="background:linear-gradient(135deg,#111820,#162030); border:1px solid #1c2838;'
        'border-radius:12px; padding:16px; margin-bottom:12px;">'
        '<h3 style="color:#00e5ff; margin:0;">📜 Application Logs</h3>'
        '<p style="color:#7a8a9e; margin:4px 0 0 0; font-size:0.85rem;">Real-time diagnostic output. Copy or save locally.</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    log_text = get_log_text()

    lc1, lc2, lc3 = st.columns(3)
    with lc1:
        # We'll use a standard Streamlit copy button or just let the user select
        # In this modular version, we'll keep it simple
        if st.button("📋 Refresh Logs View"):
            st.rerun()
            
    with lc2:
        if st.button("💾 Save to Logs Folder", key="save_logs"):
            fname = f"vostok_{datetime.now(MSK).strftime('%Y%m%d_%H%M%S')}.log"
            fpath = os.path.join(_LOGS_DIR, fname)
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(log_text)
                st.success(f"Saved: `logs/{fname}`")
                log(f"Logs saved to {fpath}")
            except Exception as e:
                st.error(f"Failed to save: {e}")
                
    with lc3:
        if st.button("🗑️ Clear Logs", key="clear_logs"):
            GLOBAL_LOG_QUEUE.clear()
            st.rerun()

    # Display log content
    st.code(log_text if log_text else "(no logs yet)", language="log")
