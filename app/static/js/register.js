(function () {
  const form = document.querySelector('[data-registration-form]');
  if (!form) return;

  const panels = Array.from(form.querySelectorAll('[data-step-panel]'));
  const indicators = Array.from(document.querySelectorAll('[data-step-indicator]'));
  let currentStep = 1;

  const panelFor = (step) => panels.find((panel) => Number(panel.dataset.stepPanel) === step);

  function showStep(step, focusFirst = true) {
    currentStep = Math.min(Math.max(step, 1), panels.length);
    panels.forEach((panel) => {
      const active = Number(panel.dataset.stepPanel) === currentStep;
      panel.hidden = !active;
      panel.setAttribute('aria-hidden', String(!active));
    });
    indicators.forEach((indicator) => {
      const indicatorStep = Number(indicator.dataset.stepIndicator);
      indicator.classList.toggle('is-active', indicatorStep === currentStep);
      indicator.classList.toggle('is-complete', indicatorStep < currentStep);
      if (indicatorStep === currentStep) indicator.setAttribute('aria-current', 'step');
      else indicator.removeAttribute('aria-current');
    });
    if (focusFirst) {
      panelFor(currentStep)?.querySelector('input:not([type="hidden"]), select')?.focus();
    }
  }

  function validateStep(step) {
    const fields = Array.from(panelFor(step)?.querySelectorAll('input, select, textarea') || []);
    for (const field of fields) {
      if (!field.checkValidity()) {
        field.reportValidity();
        field.focus();
        return false;
      }
    }
    return true;
  }

  form.addEventListener('click', (event) => {
    const nextButton = event.target.closest('[data-next-step]');
    if (nextButton) {
      if (validateStep(currentStep)) showStep(currentStep + 1);
      return;
    }
    if (event.target.closest('[data-prev-step]')) showStep(currentStep - 1);
  });

  form.addEventListener('submit', (event) => {
    for (let step = 1; step <= panels.length; step += 1) {
      if (!validateStep(step)) {
        event.preventDefault();
        showStep(step, false);
        validateStep(step);
        return;
      }
    }
  });

  const taxId = form.querySelector('#tax_id_code');
  taxId?.addEventListener('input', () => {
    taxId.value = taxId.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 16);
  });

  const firstError = form.querySelector('.field-error');
  const errorPanel = firstError?.closest('[data-step-panel]');
  showStep(errorPanel ? Number(errorPanel.dataset.stepPanel) : 1, false);
}());
