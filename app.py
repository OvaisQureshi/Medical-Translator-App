from flask import Flask, render_template, request, redirect, url_for
import json
import os
from huggingface_hub import InferenceClient

app = Flask(__name__)

DATA_FOLDER = "data"

hf_client = InferenceClient(api_key=os.environ["HF_TOKEN"])

PATIENTS = {
    "patient1": "Emma Thompson",
    "patient2": "Liam Patel",
    "patient3": "Sofia Garcia",
    "patient4": "Maya Johnson",
    "patient5": "Noah Lee"
}

SUPPORTED_LANGUAGES = ["Spanish", "Urdu", "Hindi"]


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


def translate_with_hf_llm(english_text, fields, target_language):
    medication_name = fields.get("Medication", "")
    dosage_text = fields.get("How to Take It", "")
    duration_text = fields.get("Duration", "")
    reason_text = fields.get("Reason for Use", "")
    notes_text = fields.get("Additional Notes", "")

    response = hf_client.chat.completions.create(
        model="Qwen/Qwen2.5-7B-Instruct",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a medical instruction translator. "
                    "Translate patient-friendly medication instructions safely. "
                    "Do not add, remove, or alter clinical meaning. "
                    "Return only the translated instruction text. "
                    "Do not explain anything. "
                    "Do not use quotation marks."
                )
            },
            {
                "role": "user",
                "content": f"""
Translate this medication instruction into {target_language}.

Strict rules:
- Preserve the medication name exactly: {medication_name}
- Preserve all numbers exactly.
- Preserve dosage, route, timing, and duration exactly.
- Preserve meaning exactly.
- Use simple patient-friendly language.
- Return only the translated instruction.

Locked fields:
Medication: {medication_name}
How to Take It: {dosage_text}
Duration: {duration_text}
Reason for Use: {reason_text}
Additional Notes: {notes_text}

English instruction:
{english_text}
"""
            }
        ],
        max_tokens=200
    )

    return response.choices[0].message.content.strip()


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
        translated_sentence = translate_with_hf_llm(
            english_sentence,
            english_instructions,
            target_language
        )
        translation_error = None
    except Exception as e:
        translated_sentence = None
        translation_error = str(e)

    return render_template(
        "patient.html",
        patient_id=patient_id,
        patient_name=PATIENTS.get(patient_id, "Unknown Patient"),
        patient_data=patient_data,
        english_instructions=english_instructions,
        english_sentence=english_sentence,
        translated_sentence=translated_sentence,
        target_language=target_language,
        supported_languages=SUPPORTED_LANGUAGES,
        translation_error=translation_error
    )


if __name__ == "__main__":
    app.run(debug=True)