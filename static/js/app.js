document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("input, select, textarea").forEach((element) => {
        if (!element.classList.contains("form-check-input")) {
            element.classList.add(element.tagName === "SELECT" ? "form-select" : "form-control");
        }
    });
});
