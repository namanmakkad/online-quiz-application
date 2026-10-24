/*
  Quiz page logic (navigation, timer, progress bar).
  IMPORTANT: this file never calculates the score. It only collects the
  chosen answers and sends them to Flask, which does the scoring.
*/
(function () {
    // ----- Read the data Flask put into the page -----
    var data = JSON.parse(document.getElementById("quiz-data").textContent);
    var questions = data.questions;
    var total = questions.length;

    // ----- Page elements -----
    var counterEl = document.getElementById("question-counter");
    var timerEl = document.getElementById("timer");
    var progressFill = document.getElementById("progress-fill");
    var progressText = document.getElementById("progress-text");
    var questionEl = document.getElementById("question-text");
    var optionsEl = document.getElementById("options");
    var prevBtn = document.getElementById("prev-btn");
    var nextBtn = document.getElementById("next-btn");
    var submitBtn = document.getElementById("submit-btn");
    var form = document.getElementById("quiz-form");
    var hiddenFields = document.getElementById("hidden-fields");

    // ----- State -----
    var current = 0;      // index of the question being shown
    var answers = {};     // { questionId: chosen option number (1-4) }
    var submitted = false;
    var storageKey = "quiz-answers-" + data.quiz_token;

    // Restore answers if the page was refreshed during this quiz.
    try {
        var saved = sessionStorage.getItem(storageKey);
        if (saved) { answers = JSON.parse(saved); }
    } catch (e) { answers = {}; }

    function saveAnswers() {
        try { sessionStorage.setItem(storageKey, JSON.stringify(answers)); }
        catch (e) { /* storage unavailable - the quiz still works */ }
    }

    function answeredCount() {
        return Object.keys(answers).length;
    }

    // ----- Draw the current question -----
    function render() {
        var q = questions[current];

        counterEl.textContent = "Question " + (current + 1) + " of " + total;
        questionEl.textContent = q.question;   // textContent keeps it XSS-safe

        // Build the four option buttons.
        optionsEl.innerHTML = "";
        q.options.forEach(function (text, index) {
            var optionNumber = index + 1;
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "option";
            if (answers[q.id] === optionNumber) { btn.classList.add("selected"); }

            var letter = document.createElement("span");
            letter.className = "option-letter";
            letter.textContent = String.fromCharCode(65 + index); // A, B, C, D

            var label = document.createElement("span");
            label.textContent = text;

            btn.appendChild(letter);
            btn.appendChild(label);
            btn.addEventListener("click", function () {
                if (submitted) { return; }
                answers[q.id] = optionNumber;
                saveAnswers();
                render();
            });
            optionsEl.appendChild(btn);
        });

        // Previous/Next are disabled at the first/last question.
        prevBtn.disabled = (current === 0);
        nextBtn.disabled = (current === total - 1);

        // Progress bar shows how much of the quiz has been answered.
        var done = answeredCount();
        progressFill.style.width = (total ? (done / total) * 100 : 0) + "%";
        progressText.textContent = done + " of " + total + " answered";
    }

    prevBtn.addEventListener("click", function () {
        if (current > 0) { current--; render(); }
    });

    nextBtn.addEventListener("click", function () {
        if (current < total - 1) { current++; render(); }
    });

    // ----- Submit -----
    function submitQuiz(auto) {
        if (submitted) { return; }   // stops double submissions

        if (!auto) {
            var left = total - answeredCount();
            var msg = left > 0
                ? "You have " + left + " unanswered question(s). Submit anyway?"
                : "Submit your quiz now?";
            if (!window.confirm(msg)) { return; }
        }

        submitted = true;
        clearInterval(timerId);

        // Add one hidden input per answer, then send the form to Flask.
        hiddenFields.innerHTML = "";
        Object.keys(answers).forEach(function (qid) {
            var input = document.createElement("input");
            input.type = "hidden";
            input.name = "answer_" + qid;
            input.value = answers[qid];
            hiddenFields.appendChild(input);
        });

        try { sessionStorage.removeItem(storageKey); } catch (e) { }

        prevBtn.disabled = true;
        nextBtn.disabled = true;
        submitBtn.disabled = true;
        submitBtn.textContent = "Submitting...";
        form.submit();
    }

    submitBtn.addEventListener("click", function () { submitQuiz(false); });

    // ----- Countdown timer -----
    // We store the END time so the countdown stays accurate even if the
    // browser tab is slowed down.
    var endTime = Date.now() + data.remaining_seconds * 1000;

    function formatTime(seconds) {
        var m = Math.floor(seconds / 60);
        var s = seconds % 60;
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
    }

    function updateTimer() {
        var secondsLeft = Math.max(0, Math.ceil((endTime - Date.now()) / 1000));
        timerEl.textContent = formatTime(secondsLeft);

        if (secondsLeft <= 60) { timerEl.classList.add("timer-warning"); }

        if (secondsLeft <= 0) {
            clearInterval(timerId);
            submitQuiz(true);   // time is up: submit automatically
        }
    }

    var timerId = setInterval(updateTimer, 500);

    // ----- Start -----
    if (total === 0) {
        questionEl.textContent = "No questions are available.";
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        submitBtn.disabled = true;
        clearInterval(timerId);
    } else {
        render();
        updateTimer();
    }
})();
