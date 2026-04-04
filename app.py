from flask import Flask, render_template, request, redirect, url_for
import json
import os
from transformers import MarianMTModel, MarianTokenizer

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

translation_models = {}


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


def get_translation_model(target_language):
    model_map = {
        "Spanish": "Helsinki-NLP/opus-mt-en-es",
        "French": "Helsinki-NLP/opus-mt-en-fr",
        "German": "Helsinki-NLP/opus-mt-en-de"
    }

    model_name = model_map.get(target_language, "Helsinki-NLP/opus-mt-en-es")

    if model_name not in translation_models:
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)

        translation_models[model_name] = {
            "tokenizer": tokenizer,
            "model": model
        }

    return translation_models[model_name]


def translate_with_local_model(text_to_translate, target_language):
    if text_to_translate == "Not provided":
        return text_to_translate

    model_bundle = get_translation_model(target_language)
    tokenizer = model_bundle["tokenizer"]
    model = model_bundle["model"]

    inputs = tokenizer(
        [text_to_translate],
        return_tensors="pt",
        padding=True,
        truncation=True
    )

    translated_tokens = model.generate(**inputs)
    translated_text = tokenizer.decode(translated_tokens[0], skip_special_tokens=True)

    return translated_text


def translate_instruction_fields(fields, target_language):
    translated_fields = {}

    for label, value in fields.items():
        if value == "Not provided":
            translated_fields[label] = value
        else:
            translated_fields[label] = translate_with_local_model(value, target_language)

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
        translated_sentence = translate_with_local_model(
            english_sentence,
            target_language
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
    app.run(debug=True)