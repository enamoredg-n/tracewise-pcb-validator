const API_BASE = "http://127.0.0.1:8000/api";

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed.");
  }
  return payload;
}

export async function fetchBootstrap() {
  const response = await fetch(`${API_BASE}/bootstrap`);
  return readJson(response);
}

export async function runValidationRequest({
  candidateFile,
  referenceFile,
  rules,
  tolerances,
  useBundledReference,
}) {
  const formData = new FormData();
  formData.append("candidate_file", candidateFile);
  if (referenceFile) {
    formData.append("reference_file", referenceFile);
  }
  formData.append("rules", JSON.stringify(rules));
  formData.append("tolerances", JSON.stringify(tolerances));
  formData.append("use_bundled_reference", String(useBundledReference));
  formData.append("include_ai", "false");
  formData.append("ai_model", "");

  const response = await fetch(`${API_BASE}/validate`, {
    method: "POST",
    body: formData,
  });

  return readJson(response);
}
