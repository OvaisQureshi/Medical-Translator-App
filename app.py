from flask import Flask, render_template, request, redirect, url_for
import json
import os
import requests

app = Flask(__name__)

DATA_FOLDER = "data"

PATIENTS = {
    "patient1": "Emma Thompson",
    "patient2": "Liam Patel",
    "patient3": "Sofia Garcia",
    "patient4": "Maya Johnson",
    "patient5": "Noah Lee"
}

SUPPORTED_LANGUAGES = ["Spanish", "French", "German"]

LANGUAGE_CODES = {
    "Spanish": "es",
    "French": "fr",
    "German": "de"
}

AZURE_TRANSLATOR_KEY = os.environ.get("AZURE_TRANSLATOR_KEY")
AZURE_TRANSLATOR_REGION = os.environ.get("AZURE_TRANSLATOR_REGION")
AZURE_TRANSLATOR_ENDPOINT = os.environ.get(
    "AZURE_TRANSLATOR_ENDPOINT",
    "https://api.cognitive.microsofttranslator.com"
)


def load_patient_data(patient_id):
    file_path = os.path.join(DATA_FOLDER, f"{patient_id}.json")

    if not os.path.exists(file_path):
        return None

    with open(file_path, "r") as file:
        return json.load(file)


def extract_medication_fields(patient_data):
    medication = patient_data.get("medication", {}).get("concept", {}).get("text", "Not provided")
    status = patient_data.get("status", "Not provided")
    intent = patient_data.get("intent", "Not provided")
    subject = patient_data.get("subject", {}).get("reference", "Not provided")
    dosage = patient_data.get("dosageInstruction", {}).get("text", "Not provided")

    duration_data = patient_data.get("effectiveTimingDuration", {})
    duration_value = duration_data.get("value")
    duration_unit = duration_data.get("unit")

    if duration_value is not None and duration_unit:
        duration = f"{duration_value} {duration_unit}"
    else:
        duration = "Not provided"

    reasons_list = patient_data.get("reason", [])
    if reasons_list and "concept" in reasons_list[0]:
        reason = reasons_list[0]["concept"].get("text", "Not provided")
    else:
        reason = "Not provided"

    notes_list = patient_data.get("note", [])
    if notes_list and "text" in notes_list[0]:
        note = notes_list[0].get("text", "Not provided")
    else:
        note = "Not provided"

    return {
        "Medication": medication,
        "Prescription Status": status,
        "Prescription Intent": intent,
        "Patient Reference": subject,
        "How to Take It": dosage,
        "Duration": duration,
        "Reason for Use": reason,
        "Additional Notes": note
    }


def build_english_instruction_sentence(fields):
    how_to_take = fields.get("How to Take It", "Not provided")
    duration = fields.get("Duration", "Not provided")
    reason = fields.get("Reason for Use", "Not provided")
    notes = fields.get("Additional Notes", "Not provided")

    sentence_parts = []

    if how_to_take != "Not provided":
        sentence_parts.append(how_to_take)

    if duration != "Not provided":
        sentence_parts.append(f"for {duration}")

    sentence = " ".join(sentence_parts).strip()

    if sentence == "":
        sentence = "Instruction not available."
    elif not sentence.endswith("."):
        sentence += "."

    if reason != "Not provided":
        sentence += f" Reason for use: {reason}."

    if notes != "Not provided":
        sentence += f" Note: {notes}."

    return sentence


def get_protected_terms(fields):
    medication_name = fields.get("Medication", "")
    how_to_take = fields.get("How to Take It", "")
    duration = fields.get("Duration", "")

    protected_terms = []

    if medication_name and medication_name != "Not provided":
        protected_terms.append(medication_name)

    # Optional: protect full duration string like "7 days"
    if duration and duration != "Not provided":
        protected_terms.append(duration)

    # You can add more protected terms later if needed.
    return protected_terms


def protect_terms(text, protected_terms):
    protected_map = {}
    protected_text = text

    for i, term in enumerate(protected_terms):
        placeholder = f"__PROTECTED_{i}__"
        if term and term in protected_text:
            protected_text = protected_text.replace(term, placeholder)
            protected_map[placeholder] = term

    return protected_text, protected_map


def restore_terms(text, protected_map):
    restored_text = text

    for placeholder, original_term in protected_map.items():
        restored_text = restored_text.replace(placeholder, original_term)

    return restored_text


def translate_with_microsoft(text_to_translate, target_language, protected_terms=None):
    if text_to_translate == "Not provided":
        return text_to_translate

    if not AZURE_TRANSLATOR_KEY:
        raise ValueError("Missing AZURE_TRANSLATOR_KEY environment variable.")

    language_code = LANGUAGE_CODES.get(target_language)
    if not language_code:
        raise ValueError(f"Unsupported language: {target_language}")

    protected_terms = protected_terms or []
    protected_text, protected_map = protect_terms(text_to_translate, protected_terms)

    url = f"{AZURE_TRANSLATOR_ENDPOINT}/translate"
    params = {
        "api-version": "3.0",
        "from": "en",
        "to": language_code
    }

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_TRANSLATOR_KEY,
        "Content-Type": "application/json; charset=UTF-8"
    }

    if AZURE_TRANSLATOR_REGION:
        headers["Ocp-Apim-Subscription-Region"] = AZURE_TRANSLATOR_REGION

    body = [
        {"Text": protected_text}
    ]

    response = requests.post(url, params=params, headers=headers, json=body, timeout=20)
    response.raise_for_status()

    response_json = response.json()

    translated_text = response_json[0]["translations"][0]["text"]
    translated_text = restore_terms(translated_text, protected_map)

    return translated_text


def translate_instruction_fields(fields, target_language):
    translated_fields = {}
    protected_terms = get_protected_terms(fields)

    for label, value in fields.items():
        if value == "Not provided":
            translated_fields[label] = value
        elif label in {"Medication", "Duration"}:
            # Keep key medical details exactly as-is.
            translated_fields[label] = value
        else:
            translated_fields[label] = translate_with_microsoft(
                value,
                target_language,
                protected_terms=protected_terms
            )

    return translated_fields


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        patient_id = request.form.get("patient_id")
        return redirect(url_for("patient_page", patient_id=patient_id))

    return render_template("index.html", patients=PATIENTS)


@app.route("/patient/<patient_id>")
def patient_page(patient_id):
    patient_data = load_patient_data(patient_id)

    if patient_data is None:
        return "Patient data not found", 404

    english_instructions = extract_medication_fields(patient_data)
    english_sentence = build_english_instruction_sentence(english_instructions)

    target_language = request.args.get("lang", "Spanish")
    if target_language not in SUPPORTED_LANGUAGES:
        target_language = "Spanish"

    try:
        protected_terms = get_protected_terms(english_instructions)

        translated_sentence = translate_with_microsoft(
            english_sentence,
            target_language,
            protected_terms=protected_terms
        )

        translated_fields = translate_instruction_fields(
            english_instructions,
            target_language
        )

        translation_error = None
    except Exception as e:
        translated_sentence = None
        translated_fields = {}
        translation_error = str(e)

    return render_template(
        "patient.html",
        patient_id=patient_id,
        patient_name=PATIENTS.get(patient_id, "Unknown Patient"),
        patient_data=patient_data,
        english_instructions=english_instructions,
        translated_fields=translated_fields,
        english_sentence=english_sentence,
        translated_sentence=translated_sentence,
        target_language=target_language,
        supported_languages=SUPPORTED_LANGUAGES,
        translation_error=translation_error
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)