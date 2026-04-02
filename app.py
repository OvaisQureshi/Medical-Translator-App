from flask import Flask, render_template, request, redirect, url_for
import json
import os

app = Flask(__name__)

DATA_FOLDER = "data"

PATIENTS = {
    "patient1": "Emma Thompson",
    "patient2": "Liam Patel",
    "patient3": "Sofia Garcia",
    "patient4": "Maya Johnson",
    "patient5": "Noah Lee"
}


def load_patient_data(patient_id):
    file_path = os.path.join(DATA_FOLDER, f"{patient_id}.json")

    if not os.path.exists(file_path):
        return None

    with open(file_path, "r") as file:
        return json.load(file)


def generate_english_instructions(patient_data):
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

    instructions = {
        "Medication": medication,
        "Prescription Status": status,
        "Prescription Intent": intent,
        "Patient Reference": subject,
        "How to Take It": dosage,
        "Duration": duration,
        "Reason for Use": reason,
        "Additional Notes": note
    }

    return instructions


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

    english_instructions = generate_english_instructions(patient_data)

    return render_template(
        "patient.html",
        patient_id=patient_id,
        patient_name=PATIENTS.get(patient_id, "Unknown Patient"),
        patient_data=patient_data,
        english_instructions=english_instructions
    )


if __name__ == "__main__":
    app.run(debug=True)