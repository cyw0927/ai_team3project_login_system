document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form.score-weight-form");
  if (!form) return;

  const personalInput = form.querySelector("input[name='personal_weight']");
  const teamInput = form.querySelector("input[name='team_weight']");
  const equals = form.querySelector(".weight-equals");
  if (!personalInput || !teamInput || !equals) return;

  const tutorField = document.createElement("div");
  tutorField.className = "weight-field tutor-weight-field";
  tutorField.innerHTML = `
    <label>튜터 팀 평가</label>
    <div class="input-group">
      <input class="form-control" type="number" min="0" max="100" name="tutor_weight" value="0" readonly>
      <span class="input-group-text">%</span>
    </div>`;
  form.insertBefore(tutorField, equals);

  const tutorInput = tutorField.querySelector("input[name='tutor_weight']");
  const teamField = teamInput.closest(".weight-field");
  const personalField = personalInput.closest(".weight-field");
  const plusAfterTeam = document.createElement("div");
  plusAfterTeam.className = "weight-plus tutor-weight-plus";
  plusAfterTeam.textContent = "+";
  form.insertBefore(plusAfterTeam, tutorField);

  if (personalField?.querySelector("label")) personalField.querySelector("label").textContent = "동료 개인 평가";
  if (teamField?.querySelector("label")) teamField.querySelector("label").textContent = "학생 팀 평가";
  equals.textContent = "= 100%";

  const policyCard = form.closest(".score-control-card");
  const policyChip = policyCard?.querySelector(".score-policy-chip");
  const policyText = policyCard?.querySelector(".section-heading-row p");
  const note = policyCard?.querySelector(".score-policy-note");

  const presetButton = document.createElement("button");
  presetButton.type = "button";
  presetButton.className = "btn btn-sm btn-outline-primary ms-auto";
  presetButton.innerHTML = '<i class="bi bi-magic me-1"></i>권장 40:30:30';
  form.insertBefore(presetButton, form.querySelector("button[type='submit']"));

  const refresh = () => {
    const team = Number.parseInt(teamInput.value || "0", 10) || 0;
    const personal = Number.parseInt(personalInput.value || "0", 10) || 0;
    const tutor = Math.max(0, 100 - team - personal);
    tutorInput.value = String(tutor);

    const valid = team >= 0 && personal >= 0 && team <= 100 && personal <= 100 && team + personal <= 100;
    tutorInput.classList.toggle("is-invalid", !valid);
    if (policyChip) policyChip.textContent = `팀 ${team}% · 개인 ${personal}% · 튜터 ${tutor}%`;
    if (policyText) policyText.textContent = "학생 팀 평가, 동료 개인 평가, 튜터 팀 평가의 비중을 조정합니다. 세 항목 합계는 100%입니다.";
    if (note) note.innerHTML = '<i class="bi bi-info-circle"></i> 튜터 평가는 학생 개인이 아니라 조 단위로 입력하며, 같은 조 학생에게 동일한 튜터 점수가 반영됩니다. 관리자 보정점수는 별도로 유지됩니다.';

    const submit = form.querySelector("button[type='submit']");
    if (submit) submit.disabled = !valid;
  };

  teamInput.addEventListener("input", refresh);
  personalInput.addEventListener("input", refresh);
  presetButton.addEventListener("click", () => {
    teamInput.value = "40";
    personalInput.value = "30";
    refresh();
  });

  const overallHeading = Array.from(document.querySelectorAll(".result-table-heading p"))[0];
  if (overallHeading) {
    const refreshFormula = () => {
      const team = Number.parseInt(teamInput.value || "0", 10) || 0;
      const personal = Number.parseInt(personalInput.value || "0", 10) || 0;
      const tutor = Math.max(0, 100 - team - personal);
      overallHeading.textContent = `최종 점수 = 학생 팀 ${team}% + 동료 개인 ${personal}% + 튜터 팀 ${tutor}% + 관리자 보정점수입니다.`;
    };
    teamInput.addEventListener("input", refreshFormula);
    personalInput.addEventListener("input", refreshFormula);
    presetButton.addEventListener("click", refreshFormula);
    refreshFormula();
  }

  refresh();
});
