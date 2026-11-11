/* Shared UI behaviour: toasts, delete confirmations, password toggle, form helpers. */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".toast").forEach(function (el) { new bootstrap.Toast(el).show(); });

  // Confirmation dialog for any <form data-confirm="message">
  var modalEl = document.getElementById("confirmModal");
  if (modalEl) {
    var modal = new bootstrap.Modal(modalEl), pending = null;
    document.addEventListener("submit", function (e) {
      var form = e.target;
      if (form.dataset && form.dataset.confirm && !form.dataset.confirmed) {
        e.preventDefault();
        pending = form;
        document.getElementById("confirmText").textContent = form.dataset.confirm;
        modal.show();
      }
    });
    document.getElementById("confirmYes").addEventListener("click", function () {
      if (pending) { pending.dataset.confirmed = "1"; modal.hide(); pending.submit(); }
    });
  }

  // Show / hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.querySelector(btn.dataset.togglePassword);
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.querySelector("i").className = show ? "bi bi-eye-slash" : "bi bi-eye";
    });
  });

  // Task form: show the DIT ID of the selected intern
  var internSelect = document.getElementById("intern_id"), dit = document.getElementById("dit_id_display");
  if (internSelect && dit) {
    var sync = function () {
      var opt = internSelect.options[internSelect.selectedIndex];
      dit.value = opt && opt.dataset.dit ? opt.dataset.dit : "";
    };
    internSelect.addEventListener("change", sync); sync();
  }

  // Assessment modal: fill with the clicked task
  var assessModal = document.getElementById("assessModal");
  if (assessModal) {
    assessModal.addEventListener("show.bs.modal", function (e) {
      var b = e.relatedTarget, f = document.getElementById("assessForm");
      f.action = b.dataset.action;
      document.getElementById("assessTitle").textContent = b.dataset.code + " - " + b.dataset.title;
      document.getElementById("assessWho").textContent = b.dataset.who;
      document.getElementById("a_status").value = b.dataset.status;
      document.getElementById("a_score").value = b.dataset.score || "";
      document.getElementById("a_remarks").value = "";
    });
  }
});
