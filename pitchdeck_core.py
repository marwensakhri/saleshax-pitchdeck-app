"""
SALESHAX Pitch Deck Generator — Core Logic
Importable module used by both CLI (pitchdeck.py) and Streamlit app.
"""

import re
import json
import hashlib
import textwrap
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import anthropic

MODEL = "claude-sonnet-4-6"
CTA_LINK = "https://meetings.hubspot.com/alex-akopjan/beratung?uuid=5596b6ee-2b06-4c9a-977a-bc7b208e170f"


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def fetch_website(domain: str) -> dict:
    if not domain.startswith("http"):
        url = f"https://{domain}"
    else:
        url = domain

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.SSLError:
        url = url.replace("https://", "http://")
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return {"url": url, "title": domain, "meta_desc": "", "text": "", "headings": [], "domain": domain, "customer_mentions": []}

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else domain
    meta_desc = ""
    meta = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta:
        meta_desc = meta.get("content", "").strip()

    body_text = " ".join(soup.get_text(" ", strip=True).split())[:3000]

    headings = []
    for tag in soup.find_all(["h1", "h2", "h3"])[:20]:
        txt = tag.get_text(strip=True)
        if txt:
            headings.append(txt)

    customer_keywords = ["kunden", "customer", "clients", "partner", "referenz",
                         "case study", "success", "nutzen", "vertrauen", "arbeiten mit"]
    customer_mentions = []
    for elem in soup.find_all(["p", "li", "span", "div"])[:200]:
        txt = elem.get_text(strip=True)
        if any(kw in txt.lower() for kw in customer_keywords) and len(txt) > 20:
            customer_mentions.append(txt[:200])
            if len(customer_mentions) >= 5:
                break

    return {
        "url": url, "domain": domain, "title": title,
        "meta_desc": meta_desc, "text": body_text,
        "headings": headings[:15], "customer_mentions": customer_mentions,
    }


def analyze_with_claude(website_data: dict, api_key: str, playbook_path: Path) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    playbook_text = ""
    if playbook_path and playbook_path.exists():
        playbook_text = playbook_path.read_text(encoding="utf-8")

    system_prompt = textwrap.dedent(f"""
        Du bist ein erfahrener B2B-Outbound-Stratege bei SALESHAX, einem deutschen Outbound-Matchmaking-System für SaaS/Software-Unternehmen.

        SALESHAX verkauft ein B2B-Outbound-Matchmaking-System an SaaS- und Software-Unternehmen im deutschsprachigen Raum (DACH).
        Das System identifiziert Entscheider mit echtem Intent, erstellt personalisierte Kampagnen und garantiert qualifizierte Leads innerhalb von 48 Stunden.

        Deine Aufgabe: Analysiere die Informationen über ein Prospect-Unternehmen und generiere präzise, personalisierte Pitch-Deck-Inhalte auf Deutsch.

        === VOLLSTÄNDIGES COLD EMAIL PLAYBOOK ===
        {playbook_text}
        === ENDE PLAYBOOK ===

        === ANPASSUNGEN FÜR PITCH-DECK-KONTEXT ===

        WICHTIG — PERSPEKTIVE DER COLD EMAIL:
        Die Cold Email wird IM NAMEN des Prospect-Unternehmens geschrieben.
        Du schreibst als ob du der Vertrieb von [company_name] wärst und DEREN potenzielle Kunden anschreibst.

        WICHTIG — FORMAT-OVERRIDE FÜR PITCH DECK:
        Nutze KONKRETE Platzhalter statt Spintax/Variablen:
        - "Guten Tag, Herr Mustermann," statt Spintax
        - "Mustermann GmbH", "München" als Platzhalter
        - KEIN Spintax — schreibe die Email als konkretes, lesbares Beispiel
        - Signatur: Konkreter Name + Rolle bei [company_name]

        WICHTIG — PLAYBOOK-PRINZIPIEN PFLICHT:
        1. Folge dem Workflow: Zielgruppen-Analyse → Trust-Kalibrierung → Opener-Typ wählen → Copy schreiben
        2. Wähle den passenden Opener-Typ aus dem Playbook
        3. Nutze einen der Vorwand-Typen aus dem Playbook
        4. BRANCHENSPRACHE: Nutze die Fachsprache der ZIELKUNDEN des Prospects
        5. Prüfe mental die Checkliste aus dem Playbook
        6. Radikal kurz — max 4-5 Sätze im Body

        === KAMPAGNEN-STRUKTUR REGELN ===
        Large Scale: Gesamte Zielgruppe, WEN + welcher Angle. Max 2 Sätze.
        Signal Based: 1-2 konkrete Trigger-Events. Max 2 Sätze.
        Micro: 1 konkretes Segment + Begründung. Max 2 Sätze.

        Schreibe alle Inhalte auf Deutsch. Sei faktisch und präzise.
    """).strip()

    user_prompt = textwrap.dedent(f"""
        Analysiere dieses Unternehmen und generiere personalisierte Pitch-Deck-Inhalte:

        Domain: {website_data['domain']}
        Website-Titel: {website_data['title']}
        Meta-Beschreibung: {website_data['meta_desc']}

        Überschriften der Website:
        {chr(10).join(f"- {{h}}" for h in website_data['headings'])}

        Hauptinhalt der Website (Auszug):
        {website_data['text'][:2000]}

        Kunden-/Partner-Erwähnungen:
        {chr(10).join(f"- {{c}}" for c in website_data.get('customer_mentions', []))}

        Generiere eine JSON-Antwort mit exakt diesen Feldern:

        {{
          "company_name": "SHORT brand name only, no GmbH/AG/SE suffixes.",
          "hero_intro": "2-3 Sätze personalisierter Intro.",
          "awareness_stage": "Solution-Aware, Problem-Aware oder No Awareness — mit Begründung",
          "awareness_text": "'<strong>Einschätzung für [Company]:</strong> [Erklärung]'",
          "icp_text": "HTML: <div class=\\"icp-g\\">\\n<span class=\\"icp-l\\">Zielgruppe</span><span>[...]</span>\\n<span class=\\"icp-l\\">Entscheider</span><span>[...]</span>\\n<span class=\\"icp-l\\">Awareness</span><span>[...]</span>\\n</div>",
          "campaign_1_large": "Large Scale Beschreibung + Lead-Magnet",
          "campaign_2_signal": "Signal Based Beschreibung + Lead-Magnet",
          "campaign_3_micro": "Micro Beschreibung + Lead-Magnet",
          "cold_email_subject": "Betreffzeile IM NAMEN von [company_name] an deren Kunden. Konkret, kein Spintax.",
          "cold_email_body": "FOLGE DEM PLAYBOOK! Email IM NAMEN von [company_name]. Konkrete Platzhalter. Jeder Absatz in <p>-Tags. Signatur: Name + Rolle.",
          "target_count": "z.B. '8.000–15.000'",
          "decision_maker_title": "z.B. 'CTO, Leitung Digitalisierung'",
          "dash_branche": "z.B. 'SaaS / Software'",
          "dash_groesse": "z.B. '50+ MA'",
          "dash_awareness": "z.B. 'Solution-Aware'",
          "dash_angle": "z.B. 'Schnellere Skalierung'",
          "tam_value": "Numerisch, min 1000 max 100000",
          "awareness_value": "0.95/0.75/0.45/0.20",
          "awareness_label": "Product-Aware/Solution-Aware/Problem-Aware/No Awareness",
          "clv_value": "Zahl, z.B. 35000"
        }}

        Antworte NUR mit dem JSON-Objekt, kein anderer Text.
    """).strip()

    message = client.messages.create(
        model=MODEL, max_tokens=2048,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    raw = message.content[0].text.strip()
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if json_match:
        raw = json_match.group(1)

    return json.loads(raw)


def build_campaign_structure_html(data: dict) -> str:
    return f"""<div class="camp-g fi">
    <div class="camp-c"><h3>Large Scale</h3><p>{data['campaign_1_large']}</p></div>
    <div class="camp-c hl"><h3 style="color:var(--bl2)">Signal Based</h3><p>{data['campaign_2_signal']}</p></div>
    <div class="camp-c"><h3>Micro</h3><p>{data['campaign_3_micro']}</p></div>
  </div>"""


def build_cold_email_html(data: dict) -> str:
    return f"""<div class="email fi">
    <div class="email-h">Betreff: {data['cold_email_subject']}</div>
    <div class="email-b">
      {data['cold_email_body']}
    </div>
  </div>"""


def fill_template(template_html: str, data: dict, website_data: dict) -> str:
    name = data.get("company_name", website_data.get("domain", ""))
    name = re.sub(r'\s*\([^)]+\)', '', name).strip()
    name = re.sub(r'\s+(GmbH|AG|SE|KG|GbR|UG|e\.V\.|Ltd|Inc|Corp|LLC)\.?\s*$', '', name, flags=re.IGNORECASE).strip()
    data["company_name"] = name

    campaign_html = build_campaign_structure_html(data)
    cold_email_html = build_cold_email_html(data)

    replacements = {
        "{{COMPANY_NAME}}": name,
        "{{COMPANY_LOGO_HTML}}": "",
        "{{HERO_INTRO}}": data["hero_intro"],
        "{{AWARENESS_TEXT}}": data["awareness_text"],
        "{{ICP_BOX}}": data["icp_text"],
        "{{CAMPAIGN_STRUCTURE}}": campaign_html,
        "{{COLD_EMAIL}}": cold_email_html,
        "{{DECISION_MAKER_TITLE}}": data["decision_maker_title"],
        "{{DASH_BRANCHE}}": data["dash_branche"],
        "{{DASH_GROESSE}}": data["dash_groesse"],
        "{{DASH_AWARENESS}}": data["dash_awareness"],
        "{{DASH_ANGLE}}": data["dash_angle"],
        '"{{TAM_VALUE}}"': f'"{data["tam_value"]}"',
        '"{{AWARENESS_VALUE}}"': f'"{data["awareness_value"]}"',
        "{{AWARENESS_LABEL}}": data["awareness_label"],
        '"{{CLV_VALUE}}"': f'"{data["clv_value"]}"',
    }

    html = template_html
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, str(value))
    return html


def deploy_to_netlify(html_content: str, company_slug: str, token: str) -> str:
    if not token:
        return ""

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    api = "https://api.netlify.com/api/v1"
    custom_domain = f"{company_slug}.saleshax.net"
    site_name = f"saleshax-{company_slug}"

    site_id = None
    resp = requests.get(f"{api}/sites?filter=all&per_page=100", headers=headers)
    if resp.ok:
        for site in resp.json():
            if (site.get("name") or "") == site_name:
                site_id = site["id"]
                break

    if not site_id:
        resp = requests.post(f"{api}/sites", headers=headers, json={"name": site_name, "custom_domain": custom_domain})
        if not resp.ok:
            raise RuntimeError(f"Netlify site creation failed: {resp.status_code}")
        site_id = resp.json()["id"]

    html_bytes = html_content.encode("utf-8")
    file_hash = hashlib.sha1(html_bytes).hexdigest()

    resp = requests.post(f"{api}/sites/{site_id}/deploys", headers=headers, json={"files": {"/index.html": file_hash}})
    if not resp.ok:
        raise RuntimeError(f"Netlify deploy failed: {resp.status_code}")

    deploy_data = resp.json()
    deploy_id = deploy_data["id"]
    required = deploy_data.get("required", [])

    if file_hash in required:
        resp = requests.put(
            f"{api}/deploys/{deploy_id}/files/index.html",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
            data=html_bytes,
        )
        if not resp.ok:
            raise RuntimeError(f"Netlify file upload failed: {resp.status_code}")

    requests.put(f"{api}/sites/{site_id}", headers=headers, json={"custom_domain": custom_domain})

    return f"https://{custom_domain}"


def generate_pitchdeck(domain: str, api_key: str, netlify_token: str,
                       template_path: Path, playbook_path: Path,
                       on_status=None) -> dict:
    """Full pipeline: scrape → analyze → generate → deploy. Returns dict with results."""
    def status(msg):
        if on_status:
            on_status(msg)

    status("Website wird analysiert...")
    website_data = fetch_website(domain)

    status(f"Claude analysiert {website_data.get('title', domain)}...")
    generated = analyze_with_claude(website_data, api_key, playbook_path)

    status("HTML wird generiert...")
    template_html = template_path.read_text(encoding="utf-8")
    final_html = fill_template(template_html, generated, website_data)

    company_slug = slugify(generated.get("company_name", domain))

    status("Wird auf Netlify deployed...")
    live_url = deploy_to_netlify(final_html, company_slug, netlify_token)

    return {
        "html": final_html,
        "company_name": generated.get("company_name", ""),
        "company_slug": company_slug,
        "live_url": live_url,
        "netlify_url": f"https://saleshax-{company_slug}.netlify.app",
        "generated": generated,
    }
