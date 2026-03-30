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

    # --- Cold Email Skill: Zielgruppen- und Offer-Signale extrahieren ---
    target_keywords = ["für", "zielgruppe", "geeignet für", "ideal für", "gedacht für",
                       "branchen", "industrie", "unternehmen ab", "mitarbeiter",
                       "who", "for teams", "for companies", "enterprise", "startup",
                       "kmu", "mittelstand", "konzern"]
    target_signals = []
    for elem in soup.find_all(["p", "li", "span", "div", "h2", "h3"])[:300]:
        txt = elem.get_text(strip=True)
        if any(kw in txt.lower() for kw in target_keywords) and 15 < len(txt) < 300:
            target_signals.append(txt[:200])
            if len(target_signals) >= 8:
                break

    offer_keywords = ["pricing", "preis", "kostenlos", "free", "demo", "test",
                      "feature", "funktion", "vorteil", "benefit", "lösung",
                      "garantie", "roi", "ersparnis", "sparen"]
    offer_signals = []
    for elem in soup.find_all(["p", "li", "span", "div", "h2", "h3"])[:300]:
        txt = elem.get_text(strip=True)
        if any(kw in txt.lower() for kw in offer_keywords) and 15 < len(txt) < 300:
            offer_signals.append(txt[:200])
            if len(offer_signals) >= 8:
                break

    social_proof_keywords = ["testimonial", "bewertung", "review", "sterne", "stars",
                             "logo", "trusted by", "vertrauen uns", "mehr als",
                             "unternehmen nutzen", "kunden weltweit", "%", "mio", "million"]
    social_proof = []
    for elem in soup.find_all(["p", "li", "span", "div", "blockquote", "figure"])[:300]:
        txt = elem.get_text(strip=True)
        if any(kw in txt.lower() for kw in social_proof_keywords) and 10 < len(txt) < 300:
            social_proof.append(txt[:200])
            if len(social_proof) >= 5:
                break

    return {
        "url": url, "domain": domain, "title": title,
        "meta_desc": meta_desc, "text": body_text,
        "headings": headings[:15], "customer_mentions": customer_mentions,
        "target_signals": target_signals, "offer_signals": offer_signals,
        "social_proof": social_proof,
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

        KRITISCH — SO SCHREIBST DU KEINE COLD EMAIL:
        ❌ VERBOTEN (generischer SaaS-Pitch):
        "Haben Sie Schwierigkeiten mit X? Ich frage, weil wir beobachten dass... Mit [Produkt] können Sie Feature A, Feature B und Feature C. Darf ich Ihnen mehr Infos schicken?"
        → Das ist ein Feature-Pitch, kein Playbook-konformer Cold Email!
        → Opener verrät sofort Verkaufsabsicht
        → Kein Playbook-Vorwand-Typ
        → Feature-Aufzählung statt konkrete Zahlen + Garantie

        ✅ SO MUSS ES AUSSEHEN (Playbook-konform):
        "Guten Tag, Herr Mustermann, stellen Sie gerade [Rolle] ein? Ich frage, weil wir aus einer Kampagne für [Branche] in München noch Zugriff auf qualifizierte Interessenten haben. Erste Ergebnisse innerhalb von 5 Tagen — garantiert. Darf ich Ihnen ein paar Beispiele schicken?"
        → Opener klingt wie Interessent/Kunde (nicht wie Verkäufer)
        → Vorwand aus Playbook (Kampagnen-Überschuss)
        → Konkrete Zahl + Zeitrahmen + Garantie
        → Low-Friction CTA
        → 4 Sätze, radikal kurz

        === COLD EMAIL SKILL — VOLLSTÄNDIGER WORKFLOW ===

        SCHRITT A — ZIELGRUPPE & OFFER VERSTEHEN:
        Leite aus den Website-Daten ab:
        1. WAS ist das Offer/Produkt? Was genau verkauft der Prospect?
        2. WER sind die Zielkunden? (Branche, Größe, Entscheider-Rolle)
        3. TAGESREALITÄT: Was beschäftigt den Empfänger im Alltag? Was nervt ihn? Wo verliert er Geld/Zeit?
        4. SCHON PROBIERT: Was hat die Zielgruppe wahrscheinlich schon versucht? (bestimmt Skeptizismus-Level)
        5. EMPFÄNGLICHKEITS-TRIGGER: Was macht sie gerade empfänglich? (Saisonalität, Gesetze, Fachkräftemangel, Marktveränderungen)
        6. NO-BRAINER-SCHWELLE: Was müsste man anbieten, damit ein sofortiges "Ja" kommt?

        SCHRITT B — AWARENESS & MARKTREIFE:
        1. AWARENESS-STAGE bestimmen: Product-Aware / Solution-Aware / Problem-Aware / No Awareness
           - Product-Aware: Direkt zum Offer, konkreter CTA
           - Solution-Aware: Differenzierung betonen, Mechanism zeigen
           - Problem-Aware: Pain ansprechen, Lösung andeuten
           - No Awareness: Curiosity-driven, Empfänglichkeits-Trigger nutzen
        2. MARKTREIFE bewerten (aus Playbook Abschnitt 4):
           - Verbrannter Markt? → Nicht als Agentur positionieren, Unique Mechanism betonen
           - Hoher Skeptizismus? → Professionell, implizite Qualifizierung, Low-Friction CTA
           - Technisch affine ZG? → Curiosity-driven, No-brainer Offer

        SCHRITT C — TRUST-KALIBRIERUNG:
        - Niedriger Skeptizismus: Direkter, konkreter Vorwand reicht
        - Mittlerer Skeptizismus: Vorwand muss stark sein, Zahlen und Social Proof wichtig
        - Hoher Skeptizismus: Professioneller Tonfall, implizite Qualifizierung ("sofern..."), Seriosität signalisieren

        SCHRITT D — VORWAND & ANKER WÄHLEN:
        1. VORWAND-TYP wählen (aus den 8 Playbook-Typen): Kampagnen-Überschuss, Kapazitäten frei, Regionale Aktivität, Erfolgreiche Besetzung, Staatliche Förderung, Case Study, Intent-Tracking, Positiver Anker
        2. SKALIERBARE ANKER suchen: Google-Bewertungen, Produkt/Angebot, regionale Präsenz, Branchenentwicklungen
           - Skalierbarkeit > Conversion. KEIN erzwungener Anker — lieber starker Branchenvorwand der bei 100% funktioniert.

        SCHRITT E — COPY SCHREIBEN:
        1. OPENER: Wähle aus den 8 Playbook-Typen. Muss wie von Interessent klingen — KEIN Pitch.
        2. BRÜCKE: "Ich frage, weil..." + gewählter Vorwand-Typ aus Schritt D.
        3. VALUE PROPOSITION: Konkrete Zahlen + Zeitrahmen + Garantie. BRANCHENSPRACHE der Zielkunden nutzen (Playbook Abschnitt 5).
        4. CTA wählen (4 Stufen nach Friction aus dem Playbook):
           - Infos schicken (niedrigste Hürde) → bei hohem Skeptizismus
           - Beispiele/Leads schicken → bei mittlerem Skeptizismus
           - Prospects vorstellen → bei SaaS/B2B
           - Telefonat → nur bei niedrigem Skeptizismus + Product-Aware
        5. BETREFFZEILE: Kurz, lokal, kein Verkaufs-Vibe.
        6. Radikal kurz — max 4-5 Sätze im Body.
        7. Prüfe mental die Checkliste aus dem Playbook (Abschnitt 7).

        === KAMPAGNEN-STRUKTUR ===
        Die drei Kampagnen-Ebenen müssen direkt aus der Zielgruppen-Analyse (Schritt A) und Awareness (Schritt B) abgeleitet werden:
        - Large Scale: Gesamte Zielgruppe + passendes Lead-Magnet basierend auf No-Brainer-Schwelle. WEN + welcher Angle. Max 2 Sätze.
        - Signal Based: Konkretes Trigger-Event aus Empfänglichkeits-Triggern (Schritt A.5). 1-2 Trigger + Reaktion. Max 2 Sätze.
        - Micro: Hochwertigstes Segment aus Zielgruppe + warum gerade die. Max 2 Sätze.

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

        Zielgruppen-Signale (wer nutzt das Produkt?):
        {chr(10).join(f"- {{t}}" for t in website_data.get('target_signals', [])) or '— Keine gefunden, bitte aus Kontext ableiten'}

        Offer-/Feature-Signale (was bieten sie an?):
        {chr(10).join(f"- {{o}}" for o in website_data.get('offer_signals', [])) or '— Keine gefunden, bitte aus Kontext ableiten'}

        Social Proof (Testimonials, Zahlen, Logos):
        {chr(10).join(f"- {{s}}" for s in website_data.get('social_proof', [])) or '— Keiner gefunden'}

        === ANALYSE-ENTSCHEIDUNGEN (PFLICHT — BEVOR DU JSON GENERIERST) ===

        Durchlaufe den Cold Email Skill-Workflow (Schritte A-E) und triff diese Entscheidungen:

        1. OFFER: Was verkauft der Prospect genau? An wen?
        2. ZIELGRUPPE: Wer sind die Zielkunden? Welche Branche, Größe, Entscheider?
        3. AWARENESS-STAGE: Product-Aware / Solution-Aware / Problem-Aware / No Awareness?
        4. MARKTREIFE: Verbrannter Markt? Hoher Skeptizismus? Technisch affine ZG?
        5. TRUST-LEVEL: Niedrig / Mittel / Hoch?
        6. VORWAND-TYP: Welcher der 8 Playbook-Vorwand-Typen passt?
        7. OPENER-TYP: Welcher der 8 Playbook-Opener-Typen passt?
        8. CTA-TYP: Welche Friction-Stufe passt? (Infos/Beispiele/Prospects/Telefonat)
        9. BRANCHENSPRACHE: Welche Fachbegriffe nutzt diese Zielgruppe? (Playbook Abschnitt 5)
        10. KAMPAGNEN: Large Scale Angle aus No-Brainer-Schwelle, Signal Based aus Triggern, Micro aus bestem Segment

        ALLE JSON-Felder müssen aus diesen 10 Entscheidungen abgeleitet sein.
        Die Cold Email muss sich lesen als hättest du dich 10 Minuten in die Zielkunden hineingedacht.

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
          "cold_email_subject": "Betreffzeile IM NAMEN von [company_name] an deren Kunden. Kurz, lokal, kein Verkaufs-Vibe. z.B. 'Anfragen München' oder 'Kurze Frage zu Mustermann GmbH'. Kein Spintax.",
          "cold_email_body": "STRIKT PLAYBOOK-KONFORM! KEINE Feature-Aufzählungen! Struktur: 1) Opener — muss wie Interessent klingen, NICHT wie Verkäufer. KEINE Frage die Verkaufsabsicht verrät. 2) 'Ich frage, weil...' + KONKRETER Vorwand-Typ aus Playbook (Kampagnen-Überschuss/Case Study/Intent-Tracking/etc). 3) Value Prop — EINE konkrete Zahl + Zeitrahmen + Garantie. KEINE Feature-Liste! 4) Low-Friction CTA. Max 4 Sätze Body total. Jeder Absatz in <p>-Tags. Signatur: Name + Rolle bei [company_name]. Platzhalter: Mustermann GmbH, München.",
          "target_count": "z.B. '8.000–15.000'",
          "decision_maker_title": "Die EXAKTEN Entscheider-Rollen der ZIELKUNDEN des Prospects. z.B. bei HR-Software: 'HR-Leiter, Personalleiter, Geschäftsführer'. MUSS mit dem Entscheider-Feld im icp_text übereinstimmen.",
          "dash_branche": "z.B. 'SaaS / Software'",
          "dash_groesse": "z.B. '50+ MA'",
          "dash_awareness": "z.B. 'Solution-Aware'",
          "dash_angle": "z.B. 'Schnellere Skalierung'",
          "tam_value": "Numerisch, min 1000 max 100000",
          "awareness_value": "0.95/0.75/0.45/0.20",
          "awareness_label": "Product-Aware/Solution-Aware/Problem-Aware/No Awareness",
          "clv_value": "Zahl, z.B. 35000"
        }}

        WICHTIG: Antworte NUR mit dem JSON-Objekt. Kein Text davor oder danach. Keine Erklärungen. Nur valides JSON. Stelle sicher dass alle Strings korrekt escaped sind (besonders Anführungszeichen in HTML-Attributen).
    """).strip()

    message = client.messages.create(
        model=MODEL, max_tokens=4096,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    raw = message.content[0].text.strip()
    # Try to extract JSON from markdown code block first
    json_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if json_match:
        raw = json_match.group(1)
    else:
        # Try to find JSON object directly (first { to last })
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]

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
    # Sanitize: Netlify site names only allow lowercase alphanumeric + hyphens
    safe_slug = re.sub(r'[^a-z0-9-]', '-', company_slug.lower()).strip('-')
    safe_slug = re.sub(r'-+', '-', safe_slug)[:60]
    custom_domain = f"{safe_slug}.saleshax.net"
    site_name = f"saleshax-{safe_slug}"

    site_id = None
    resp = requests.get(f"{api}/sites?filter=all&per_page=100", headers=headers)
    if resp.ok:
        for site in resp.json():
            if (site.get("name") or "") == site_name:
                site_id = site["id"]
                break

    if not site_id:
        # Try with custom domain first, fallback without if it fails
        resp = requests.post(f"{api}/sites", headers=headers, json={"name": site_name, "custom_domain": custom_domain})
        if not resp.ok:
            # Retry without custom domain
            resp = requests.post(f"{api}/sites", headers=headers, json={"name": site_name})
            if not resp.ok:
                raise RuntimeError(f"Netlify site creation failed: {resp.status_code} — {resp.text[:200]}")
        site_id = resp.json()["id"]
        # Set custom domain separately
        requests.put(f"{api}/sites/{site_id}", headers=headers, json={"custom_domain": custom_domain})

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

    # Wait for site to be live with valid SSL
    import time
    custom_url = f"https://{custom_domain}"
    netlify_url = f"https://{site_name}.netlify.app"

    # Try custom domain first (up to 30s)
    for _ in range(15):
        try:
            r = requests.get(custom_url, timeout=5, verify=True)
            if r.status_code == 200 and "<!DOCTYPE" in r.text[:200].upper():
                return custom_url  # Custom domain with valid SSL
        except Exception:
            pass
        time.sleep(2)

    # Fallback: netlify.app (always has SSL)
    for _ in range(5):
        try:
            r = requests.get(netlify_url, timeout=5)
            if r.status_code == 200:
                return netlify_url
        except Exception:
            pass
        time.sleep(2)

    return netlify_url


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
