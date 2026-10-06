import { ReactNode } from "react";
import { OHFF_COLOR } from "../components/chartTheme";
import { Flow, Go, Step, Steps, Table, Tip, Ui } from "./ui";

export type Topic = {
  id: string;
  group: string;
  title: string;
  summary: string;
  keywords: string;
  body: ReactNode;
};

export const GROUPS = ["Getting started", "Tutorial", "Step by step", "Use cases", "System flow", "Reference"];

const STATUS_ROWS: ReactNode[][] = [
  [<b>A · Accepted</b>, "Passed all checks", "Yes"],
  [<b>B · Accepted with warnings</b>, "Passed the critical checks, with statistical notes", "Yes, flagged"],
  [<b>C · On hold</b>, "Failed a critical check (e.g. fewer than 8 actual points, wrong unit)", "No, waiting for review"],
  [<b>X · Excluded</b>, "Excluded by an engineer's review", "No"],
];

const Swatch = ({ c }: { c: string }) => (
  <span style={{ display: "inline-block", width: 18, height: 4, borderRadius: 2, background: c, verticalAlign: "middle" }} />
);

export const TOPICS: Topic[] = [
  // ------------------------------------------------------------------ Getting started
  {
    id: "overview",
    group: "Getting started",
    title: "What This System Does",
    summary:
      "A brief overview of the system, the data used, and the workflow from historical data to Torque & Drag predicting.",
    keywords: "overview introduction wellplan friction factor ml calibration prediction directional driller",
    body: (
      <>
        <p>
          Torque &amp; Drag (T&amp;D) models and actual field measurements are prepared and recorded by the Directional Driller
          (DD) during drilling operations. The dataset includes modeled and actual hookload under pick-up, slack-off, and
          rotating conditions, as well as torque, referenced against measured depth.
        </p>
        <p>
          The Machine Learning (ML) system learns the relationship and patterns between historical T&amp;D model outputs and
          actual field measurements from previously drilled wells. Based on these learned patterns, the system generates a
          forward-looking prediction of Torque &amp; Drag behavior at upcoming drilling depths.
        </p>
        <Flow
          title="Workflow: historical data → ML → T&D prediction"
          nodes={[
            { title: "Training Data", desc: "historical wells: T&D model + actual", tone: "user", to: "/training" },
            { title: "Data Quality", desc: "A / B / C / X", tone: "system", to: "/quality" },
            { title: "Freeze dataset & train", desc: "validated on unseen wells", tone: "user", to: "/models" },
            { title: "Monitoring", desc: "well being drilled: T&D model (+ actual so far)", tone: "user", to: "/monitoring" },
            { title: "T&D prediction", desc: "N ft ahead, P10–P90, cause and effect", tone: "out", to: "/dashboard" },
            { title: "Excel / PDF", tone: "out" },
            { title: "Evaluation", desc: "prediction vs actual", tone: "out", to: "/evaluations" },
          ]}
        />
        <h3>Menus</h3>
        <Table
          head={["Menu", "Purpose"]}
          rows={[
            [<Ui>Training Data</Ui>, "Historical wells (the ML reference): bulk import from folder, upload files/templates, well list"],
            [<Ui>Monitoring</Ui>, "Wells to be drilled or being drilled: upload, predict. Never used for training"],
            [<Ui>Data Quality</Ui>, "Status A/B/C/X per well section, reasons, the engineer's review decision, quality report"],
            [<Ui>Models</Ui>, "Freeze datasets, train and compare models, accuracy report, blind test"],
            [<Ui>Dashboard</Ui>, "Charts (Hookload, Torque, Difference), prediction N ft ahead, operating limits, Excel and PDF"],
            [<Ui>Evaluations</Ui>, "Prediction compared with actual data after drilling"],
            [<Ui>How-to Guide</Ui>, "This page"],
          ]}
        />
        <h3>Key terms</h3>
        <Table
          head={["Term", "Meaning"]}
          rows={[
            ["Well section", 'One file = one section of a well (e.g. 8.5"). Quality and predictions are per well section.'],
            ["T&D model (WellPlan)", "The modelled hookload/torque. One curve per open hole friction factor (OHFF). Baseline = OHFF 0.3."],
            ["DD Calibrate", "Offsets entered by the DD at the top of the roadmap Drag/Torque sheets. A correction, not actual data."],
            ["Training Data / Monitoring", "Historical wells that teach the ML / wells being drilled that are only predicted. Never mixed."],
            ["Unseen-well validation", "Out-of-fold prediction for a training well from a model that never saw that well (a fair comparison)."],
            ["Blind test", "About 20% of the wells are locked from the start and tested only once at the end."],
            ["Uncertainty band (P10–P90)", "The range in which 80% of the actual readings are expected."],
            ["Difference (Δ)", "A − B. Right (+) = A is higher, left (−) = A is lower."],
          ]}
        />
      </>
    ),
  },
  {
    id: "quick-start",
    group: "Getting started",
    title: "Quick Start",
    summary: "One-page checklist: sign in → upload → prediction → output.",
    keywords: "quick start checklist first time tutorial practice files",
    body: (
      <>
        <Steps>
          <Step n={1} title="Sign in">
            Open the application address, enter the username and password, click <Ui>Sign in</Ui>.
          </Step>
          <Step n={2} title="Training Data → upload historical wells">
            Select the <b>Well section</b> and <b>Well type</b>, then drop the files (template or original WellPlan files).
            Check the result column: data quality A/B = used for training.
          </Step>
          <Step n={3} title="Data Quality → review status C">
            Open each C well, read the reason, choose <Ui>Accept</Ui>, <Ui>Exclude</Ui> or <Ui>Fix</Ui> with a reason.
          </Step>
          <Step n={4} title="Models → Freeze a new dataset → Train model">
            Wait 3–5 minutes. Status <b>Done + active</b> = in use. Read the report (RMSE T&amp;D model → ML).
          </Step>
          <Step n={5} title="Monitoring → upload the well being drilled">
            Select the Well section and Well type, drop the file (T&amp;D model + actual readings so far).
          </Step>
          <Step n={6} title="Dashboard → Prediction ahead">
            Enter the distance (e.g. 300 ft), click <Ui>Run prediction</Ui>. Read the cause-and-effect sentences and the shaded
            prediction window.
          </Step>
          <Step n={7} title="Output">
            <Ui>Export Excel</Ui>, <Ui>PDF</Ui>, <Ui>⬇ Prediction (.xlsx)</Ui>.
          </Step>
        </Steps>
        <Tip>
          Practice files (synthetic, not client data) for a first session: the operator runs <code>make practice-files</code>{" "}
          and shares <code>data/practice/</code> (training/, monitoring/, README.txt with the section and type to select). Use
          the training practice files on a practice installation only, or delete the PRACTICE wells afterwards.
        </Tip>
      </>
    ),
  },
  {
    id: "tutorial-test-model",
    group: "Tutorial",
    title: "Tutorial: test the model on a well",
    summary:
      "For first-time users: upload a well in Monitoring, read the result, prediction 300 ft ahead and check the ML against the actual readings.",
    keywords: "tutorial beginner test model monitoring upload section type prediction check against actual accuracy tolerance step by step",
    body: (
      <>
        <Tip>
          <b>No experience needed.</b> Follow the parts in order. Words in a grey box such as <Ui>Monitoring</Ui> are exactly what
          you see on the screen. One well takes about 10 minutes.
        </Tip>

        <h3>Part 0 — The idea in plain words</h3>
        <Table
          head={["Word", "What it means"]}
          rows={[
            ["T&D model (WellPlan)", "What the planning software calculates for hookload and torque, one curve per friction factor (OHFF)."],
            ["Actual", "What was really read on the rig while drilling (pick up, slack off, rotating weight, torque)."],
            ["ML prediction", "The system's estimate. It learned from many drilled wells how far the T&D model usually is from the actual readings."],
            ["Training Data", "Old wells the ML learned from. You do not touch these to test the model."],
            ["Monitoring", "Wells you want a prediction for. Uploading here never changes the ML, so it is the safe place to test."],
            ["Tolerance", "The client's pass mark: the ML is good when it is within 10 klbf (hookload) and 2 kft-lbf (torque) of the actual reading."],
          ]}
        />
        <p>
          <b>Testing the model</b> = give the system a well it has never seen, let it predict, and compare the prediction with
          what was really read on the rig. The system does the comparison for you and shows a percentage: the share of actual
          readings that the ML hit within the tolerance. <b>90% or more is good</b>.
        </p>
        <Flow
          title="The whole test in one line"
          nodes={[
            { title: "1. Check a model is active", tone: "user", to: "/models" },
            { title: "2. Monitoring: choose section & type", tone: "user", to: "/monitoring" },
            { title: "3. Upload the file", tone: "user" },
            { title: "4. Read the result", tone: "out" },
            { title: "5. Dashboard: prediction 300 ft", tone: "user", to: "/dashboard" },
            { title: "6. Check against actual", tone: "out" },
            { title: "7. Download Excel / PDF", tone: "out" },
          ]}
        />

        <h3>Part 1 — Before you start (2 minutes)</h3>
        <Steps>
          <Step n={1} title="Sign in">
            Open the application address, type the username and password, click <Ui>Sign in</Ui>.
          </Step>
          <Step n={2} title="Check that a model is active">
            Click <Ui>Models</Ui> in the top bar. In <b>Model history</b> one row must show the status <b>Done</b> with the
            green label <b>active</b>. If there is none, a model must be trained first (see topic 4).
          </Step>
          <Step n={3} title="Prepare the file of the well you want to test">
            One Excel file for one section of one well: the original WellPlan report (.xlsm), the T&amp;D roadmap (.xlsx), or
            the system template. For a real test the file should <b>also contain actual readings</b> (sheet "T&amp;D Actual
            Reading" or "Drilling Data"), otherwise there is nothing to compare with.
          </Step>
          <Step n={4} title="Find out the well section and the well type">
            <b>Well section</b> = the hole size of this file, usually in the file name (e.g. <code>_8.5in</code> means 8.5").{" "}
            <b>Well type</b>: <b>J</b> = builds up and holds the angle, <b>S</b> = builds up, holds, then drops back,{" "}
            <b>Horizontal</b> = ends near 90° inclination. Ask the DD or the well plan if you are not sure.
          </Step>
        </Steps>

        <h3>Part 2 — Upload the well in Monitoring</h3>
        <Steps>
          <Step n={1} title="Click Monitoring in the top bar">
            The page "Upload a monitoring well (prediction only)" opens. It has five numbered steps.
          </Step>
          <Step n={2} title="Step 1 on the page: select the Well section and the Well type">
            Open the <Ui>Well section</Ui> list and pick the hole size (e.g. <b>8.5"</b>). Open <Ui>Well type</Ui> and pick{" "}
            <b>J</b>, <b>S</b> or <b>Horizontal</b>. <Ui>Well name</Ui> is optional: leave it empty to read it from the file.
            <br />
            Until both lists are chosen the grey box in step 4 says "Select the well section and well type first".
          </Step>
          <Step n={3} title="Step 2 (optional): template">
            Only if you have no original file: click <Ui>⬇ Monitoring well template (.xlsx)</Ui>, fill it in following the
            "Instructions" and "Example" sheets, save it.
          </Step>
          <Step n={4} title="Step 4: upload">
            Drag the file onto the box, or click the box and choose the file. Wait a few seconds: "Importing and checking the
            file…", then "Predicting with the active model…".
          </Step>
          <Step n={5} title="Step 5: read the prediction result">
            A table appears with one row per operation (Pick up, Slack off, Rotating weight, Torque off bottom, Torque on
            bottom) at the deepest depth:
            <ul>
              <li>
                <b>T&amp;D Model (OHFF 0.3)</b> = the planning value, <b>ML prediction</b> = the system's value,{" "}
                <b>Uncertainty band (P10–P90)</b> = the range in which the reading will most likely fall,{" "}
                <b>ML − T&amp;D Model</b> = how much the system corrects the plan.
              </li>
              <li>Yellow messages are warnings worth reading (e.g. a well type rare in the training data).</li>
            </ul>
            Click <Ui>Open dashboard (prediction N ft ahead)</Ui> to continue.
          </Step>
        </Steps>
        <Tip kind="warn">
          If you get a red message instead, the file could not be read: the reason is listed per sheet. Typical causes: the
          wrong file type, renamed column headers, or a section that does not match the file. Fix the file and upload again.
        </Tip>

        <h3>Part 3 — Look at the charts (Dashboard)</h3>
        <Steps>
          <Step n={1} title="The well is already selected">
            In <Ui>Well</Ui> it is shown with the tag <b>[Monitoring]</b>. Leave <Ui>Units</Ui> on Imperial (ft, klbf, ft-lbf).
          </Step>
          <Step n={2} title="Hookload panel (top)">
            Blue lines = T&amp;D model per OHFF (lighter blue = lower OHFF), names like <b>PU - OHFF : 0.3</b>. Orange line =
            ML prediction (<b>PU - ML</b>). Green points = actual readings (<b>PU Actual</b>). <b>Good sign</b>: the green points
            sit on or close to the orange line.
          </Step>
          <Step n={3} title="Torque panel and Difference panel">
            Same idea for torque. The Difference panel shows actual minus model: points near the black zero line = small
            error.
          </Step>
          <Step n={4} title="Metrics for this well (bottom right)">
            Column <b>Within tol. WP → ML</b>: e.g. "70% → <b>96%</b>" means 70% of the actual readings were within the
            tolerance of the T&amp;D model and 96% within the tolerance of the ML. This is the main test result for the whole
            well.
          </Step>
        </Steps>

        <h3>Part 4 — Test the prediction 300 ft ahead</h3>
        <p>
          The real question while drilling is: <i>how good is the prediction for the next 300 ft?</i> You can test it on a well
          that already has the actual readings, by pretending you are drilling at an earlier depth.
        </p>
        <Steps>
          <Step n={1} title="Scroll down to the panel Prediction ahead">Below the charts.</Step>
          <Step n={2} title="Distance: 300">The number of feet to prediction.</Step>
          <Step n={3} title="From depth: an earlier depth (for the test)">
            Example: the actual readings go down to 9,500 ft. Type <b>9,000</b>. The prediction then only uses the data above
            9,000 ft, exactly as if the rig were at 9,000 ft now. (Leave it empty for a real prediction from the last reading.)
          </Step>
          <Step n={4} title="Local bias correction: leave it ticked">
            It shifts the prediction using the last actual readings above the start depth, like the DD's calibration. It is on by
            default because it is the most accurate.
          </Step>
          <Step n={5} title="Click Run prediction — the charts jump to the prediction">
            The page scrolls up to the charts and zooms to the prediction window automatically. What you see:
            <ul>
              <li>
                Two dashed purple lines: <b>Prediction start · 9,000 ft</b> and <b>Prediction end · 9,300 ft (+300 ft)</b>, with the
                window between them lightly shaded.
              </li>
              <li>
                A <b>thick purple line</b> per operation = <b>the prediction</b>: where hookload/torque is expected to go over the
                next 300 ft. The shaded purple band around it = the likely range (P10–P90).
              </li>
              <li>
                At the end of each purple line the <b>prediction value</b> is written, e.g. "PU 128 klbf @ 9,300 ft".
              </li>
              <li>Green points inside the window = actual readings the prediction is tested against.</li>
            </ul>
            <Ui>Show whole well</Ui> (above the charts) goes back to the full depth; <Ui>Zoom to prediction</Ui> returns to the
            window.
          </Step>
          <Step n={6} title="Read the table">
            <ul>
              <li>
                <b>Check against actual</b> — the test result: e.g. "T&amp;D 60% · ML + bias <b>100%</b> (n=10)" = of the 10
                actual readings in the next 300 ft, the T&amp;D model hit 60% and the ML 100% within the tolerance.
              </li>
              <li>
                <b>Expected accuracy</b> — how the model did for the same distance on many wells it never saw (e.g. "99% &lt;
                10 klbf"). Your result should be close to it.
              </li>
              <li>
                <b>Cause and effect</b> sentences explain why the values rise or fall (inclination, dogleg, T&amp;D model) and
                whether an operating limit is reached.
              </li>
            </ul>
          </Step>
          <Step n={7} title="Repeat at other depths">
            Try 2–3 start depths (e.g. top, middle, bottom of the section) to see if the model is good everywhere.
          </Step>
        </Steps>

        <h3>Part 5 — Download the result</h3>
        <Steps>
          <Step n={1} title="Export Excel (top of the dashboard)">
            The client's format "OUTPUT … Multiple T&amp;D Road Map": Summary Outputs (actual vs ML table, performance metric),
            drag and torque graphs, PU/SO/ROT MW sheets.
          </Step>
          <Step n={2} title="PDF">A printable summary with the charts.</Step>
          <Step n={3} title="⬇ Prediction (.xlsx)">The 300 ft prediction with the check and the cause-and-effect sentences.</Step>
        </Steps>

        <h3>Part 6 — The model's own test report (optional)</h3>
        <Steps>
          <Step n={1} title="Models → Report on the active model">
            Main table, column <b>Within tolerance T&amp;D → ML</b>: result on all training wells, each judged by a model that
            never saw it. Column <b>Blind within tolerance</b>: result on the locked blind-test wells.
          </Step>
          <Step n={2} title="Tab Prediction backtest">
            How often the prediction 300 / 600 / 1,000 ft ahead was within tolerance on unseen wells, with and without bias
            correction.
          </Step>
        </Steps>

        <h3>Good to know</h3>
        <Table
          head={["Situation", "What to do"]}
          rows={[
            ["The upload box is grey", "Choose Well section and Well type first (step 1)."],
            ["\"No active model yet\"", "Train a model in Models first, or ask the administrator."],
            ["The prediction stops before 300 ft", "The WellPlan results end there; the ML needs them as input."],
            ["No 'Check against actual' column", "There are no actual readings in the window: enter an earlier From depth."],
            ["Does my test change the ML?", "No. Monitoring wells are never used for training."],
            ["Remove the test well afterwards", "Monitoring → list of wells → Delete."],
            ["Want to practise without client data?", "Use the practice files (Quick Start): data/practice/monitoring. They are synthetic: good for learning the screens, but their accuracy numbers say nothing about the real model. Test the model with real wells."],
          ]}
        />
        <Go to="/monitoring">Open Monitoring</Go>
      </>
    ),
  },
  {
    id: "reading-charts",
    group: "Tutorial",
    title: "Reading the charts: every line and shading",
    summary: "What each colour, line, point, shaded area and table on the dashboard means, in plain words.",
    keywords: "read chart legend line colour blue orange green purple red dashed dotted shading band P10 P90 prediction window difference metrics table beginner",
    body: (
      <>
        <Tip>
          Depth goes <b>down</b> the chart (deeper = lower), values go <b>right</b> (heavier / more torque = further right). A
          prediction is good when the <b>green points sit on its line</b>. The client's pass mark: within 10 klbf (hookload) and
          2 kft-lbf (torque).
        </Tip>
        <h3>Colours</h3>
        <Table
          head={["Colour", "What it is"]}
          rows={[
            [<><Swatch c={OHFF_COLOR["0.1"]} /> <Swatch c={OHFF_COLOR["0.5"]} /> Blue lines</>, "T&D model (WellPlan), one line per OHFF: lighter = lower friction factor, darker = higher. Same colour for the same OHFF in every chart."],
            [<><Swatch c="#eb6834" /> Orange line</>, "ML prediction for the whole well (PU - ML, SO - ML, ROT - ML)."],
            [<><Swatch c="#eb6834" /> Orange dashed lines</>, "Only when 'Uncertainty band (P10–P90)' is ticked: 80% of the actual readings are expected between the two dashed lines (design target). The real share is in Models → report, column 'Inside P10–P90 band': CV ≈ 80% by construction, blind = the test on unseen wells."],
            [<><span style={{ color: "#1baf7a" }}>● ▲ ■</span> Green points</>, "Actual readings from the rig: ● pick up / torque off bottom, ▲ slack off / torque on bottom, ■ rotating weight."],
            [<><Swatch c="#4a3aa7" /> Thick purple line</>, "THE FORECAST N ft ahead (bias-corrected). The value at its end is written next to the ◆, e.g. 'PU 254 klbf @ 8,900 ft'."],
            ["Faded purple strip around the purple line", "Prediction range P10–P90: where the reading will most likely (target 80%) fall. How well the 80% holds: Models → report, column 'Inside P10–P90 band (CV / blind)'."],
            ["Very light purple shading across the chart, between two dashed purple lines", "The prediction window (from 'Prediction start' to 'Prediction end'). It only marks the area; it is not a value."],
            [<><span style={{ color: "#e34948" }}>┆</span> Red dotted vertical line</>, "Operating limit (e.g. max pick up, top drive torque)."],
            ["Very light red shading", "Depths below the first point where the ML prediction reaches the limit."],
            ["Light yellow shading", "Flagged intervals: |difference| above the threshold in 'Flag intervals' (hidden while a prediction is shown)."],
            ["Black dashed horizontal line (on hover)", "Guide line at the mouse depth in all panels; the bar below the charts lists every value at that depth (WP = T&D model, ML, Act = actual)."],
          ]}
        />
        <h3>The three panels</h3>
        <Table
          head={["Panel", "How to read it"]}
          rows={[
            ["Hookload", "Left group = SO (slack off, lightest), middle = ROT (one line), right = PU (pick up, heaviest). Normal order left to right: SO ≤ ROT ≤ PU."],
            ["Torque", "Left group = Torque Off Bottom (rotating above the bottom), right group = Torque On Bottom (drilling)."],
            ["Difference (Δ)", "A − B for one operation. Black vertical line = 0 = exactly equal. Blue dots = T&D model − actual, orange diamonds = ML − actual, purple line = ML − T&D model. Right (+) = A is higher, left (−) = A is lower. Closer to the black line = more accurate."],
          ]}
        />
        <h3>Tables</h3>
        <Table
          head={["Table / column", "Meaning"]}
          rows={[
            ["Prediction: Bias-corrected at end", "The prediction value used (= the value at the end of the purple line). '(bias −20.4)' = the last readings were 20.4 below the ML, so the prediction was moved down by that."],
            ["Prediction: P10–P90 at end", "Likely range at the end of the window."],
            ["Prediction: Expected accuracy", "How often this model was within tolerance for this distance on wells it never saw."],
            ["Prediction: Check against actual", "Only when testing with an earlier From depth: prediction vs the readings that follow ('ML + bias 100% (n=3)' = all 3 readings within tolerance)."],
            ["Prediction: Main drivers / Cause and effect", "Why the values change (T&D model trend, inclination, dogleg …) and whether a limit is reached."],
            ["Metrics: RMSE / MAPE", "Average error in units / percent — smaller is better."],
            ["Metrics: R²", "How well the curve shape follows the actual readings — closer to 1 is better."],
            ["Metrics: Within tol. WP → ML", "The client's measure: share of readings within 10 klbf / 2 kft-lbf, for the T&D model and for the ML. 90% or more is good."],
            ["Operating limits: … reaches", "First depth where the ML, the ML band or the T&D model reaches the limit; 'not reached' = never. Minimum ML margin < 0 = the limit is exceeded."],
          ]}
        />
        <Tip>
          Too busy? Untick operations you do not need, untick <Ui>All OHFF curves</Ui> to keep only OHFF 0.3, or drag a box to
          zoom. <Ui>Show whole well</Ui> / <Ui>Reset zoom</Ui> brings back the full depth. A version with numbered screenshots
          (Bahasa Indonesia) is in <code>docs/panduan_membaca_grafik.md</code>.
        </Tip>
      </>
    ),
  },
  {
    id: "login",
    group: "Getting started",
    title: "Sign in and sign out",
    summary: "Sign in with the admin account; 8-hour session; 15-minute lock after failed attempts.",
    keywords: "login sign in password forgot locked sign out session",
    body: (
      <>
        <Steps>
          <Step n={1} title="Open the application address">
            Laptop: <code>http://localhost:8401</code>. Server: the <code>https://…</code> address from the administrator.
          </Step>
          <Step n={2} title="Enter the username and password">
            Click the eye icon in the password field to show or hide the password.
          </Step>
          <Step n={3} title="Click Sign in">
            You land on <Ui>Training Data</Ui>. The session lasts 8 hours.
          </Step>
          <Step n={4} title="Sign out">
            Click <Ui>Sign out</Ui> at the top right.
          </Step>
        </Steps>
        <Tip kind="warn">
          After 5 wrong passwords, sign-in is locked for 15 minutes. Forgot the password: the operator runs{" "}
          <code>make password</code> on the server (this also removes the lock).
        </Tip>
      </>
    ),
  },

  // ------------------------------------------------------------------ Step by step
  {
    id: "prepare-files",
    group: "Step by step",
    title: "1. Preparing well files",
    summary: "Accepted formats: original WellPlan files (report or roadmap) or the template.",
    keywords: "file format excel xlsx xlsm roadmap wellplan report template section file name calibrate",
    body: (
      <>
        <p>
          <b>One Excel file = one well section.</b> Three kinds of file are accepted:
        </p>
        <Table
          head={["Kind", "Recognised by", "Notes"]}
          rows={[
            [
              <b>WellPlan report (.xlsm)</b>,
              "sheets Summary, Tripping Load Analysis, Off Bottom Torque analysis, Survey Outputs, Drilling Data",
              "Survey and actual drilling data are read too",
            ],
            [
              <b>T&amp;D roadmap (.xlsx)</b>,
              "sheets Drag, Torque, T&D Actual Reading",
              "DD Calibrate offsets (Drag row 2, Torque C2/C3) are read; 'Graph reference' columns are ignored",
            ],
            [<b>Template</b>, "downloaded from the application; sheets Well Info, Drag, Torque, (T&D), Survey", "Same layout as the roadmap"],
          ]}
        />
        <p>
          <b>Before every upload you select the Well section and Well type.</b> The selection wins over the file; if the file
          says something else the import shows a warning.
        </p>
        <Tip>
          .xlsm files are read without running macros. Numbers stored as text and the units Klbs/kip/1000 lbf/ft-lbf/kft-lbf are
          recognised automatically. Old templates (sheet "Info Sumur") are still accepted.
        </Tip>
      </>
    ),
  },
  {
    id: "bulk-import",
    group: "Step by step",
    title: "2a. Bulk import from folder (Training Data)",
    summary: "The fastest way for dozens of historical wells: Scan folder.",
    keywords: "bulk import folder inbox scan processed rejected training",
    body: (
      <>
        <Steps>
          <Step n={1} title="Put the files in the inbox folder">
            The operator copies files to <code>data/inbox/&lt;J|S|Horizontal&gt;/&lt;well&gt;/</code> (client data:{" "}
            <code>make inbox-training</code>). Folder name = well code, parent folder = well type.
          </Step>
          <Step n={2} title="Training Data → Bulk import from folder">
            The panel shows how many files are waiting.
          </Step>
          <Step n={3} title="Click Scan folder">
            About 30 seconds for 94 files. Files modified less than 1 minute ago are skipped (they may still be copying).
          </Step>
          <Step n={4} title="Read the result">
            Tab <Ui>By well section</Ui>: data quality A/B/C + reasons. Tab <Ui>By file</Ui>: accepted / accepted with warnings /
            duplicate / skipped / rejected + reason.
          </Step>
        </Steps>
        <Tip>
          The folder scan always imports as <b>Training Data</b>. Accepted files move to <code>data/processed/</code>, rejected
          files to <code>data/rejected/</code> with a <code>.reason.txt</code>. The same file is never imported twice; a file
          whose content changed becomes a new version.
        </Tip>
        <Go to="/training">Open Training Data</Go>
      </>
    ),
  },
  {
    id: "upload-training",
    group: "Step by step",
    title: "2b. Upload training data",
    summary: "Select section and type, download the template, fill in, upload, read the data quality.",
    keywords: "upload template training data import excel well info actual reading section type",
    body: (
      <>
        <Steps>
          <Step n={1} title="Training Data → select Well section and Well type">
            Both are required; the upload area stays disabled until they are selected.
          </Step>
          <Step n={2} title="Download the template (optional)">
            Have the original WellPlan file? Skip steps 2–3 and upload it directly.
          </Step>
          <Step n={3} title="Fill in the template">
            <b>Well Info</b>: name, section, type, block weight. <b>Drag</b>: depth (ft) + hookload (kip) Tripping In / Tripping
            Out / Rotating Off Bottom per OHFF, optional DD Calibrate offsets in row 2. <b>Torque</b>: Rotating On/Off Bottom
            (ft-lbf) per OHFF, optional Calibrate in C2/C3. <b>T&amp;D Actual Reading</b>: field readings (at least 8 depths).{" "}
            <b>Survey</b> optional. See the Example sheets.
          </Step>
          <Step n={4} title="Upload">Drop the files (several at once is fine, same section and type).</Step>
          <Step n={5} title="Result">
            Per file: import status, well, section, type, <b>data quality</b>. A/B are used in the next training run.
          </Step>
        </Steps>
        <Tip kind="warn">Do not rename headers or insert columns in the template. Use a dot as the decimal separator.</Tip>
        <Go to="/training">Open Training Data</Go>
      </>
    ),
  },
  {
    id: "quality",
    group: "Step by step",
    title: "3. Checking data quality",
    summary: "Status A/B/C/X, reading the reasons, recording a review decision.",
    keywords: "data quality status a b c x on hold review accept exclude fix report",
    body: (
      <>
        <Table head={["Status", "Meaning", "Used for training?"]} rows={STATUS_ROWS} />
        <Steps>
          <Step n={1} title="Open Data Quality">
            <Ui>Data group</Ui> = Training Data by default. The A/B/C/X tiles filter the list.
          </Step>
          <Step n={2} title="Click a well">All checks are shown: critical (red), warning (yellow), pass.</Step>
          <Step n={3} title="Record a decision">
            <Ui>Accept (with a note)</Ui> (C → B), <Ui>Exclude from training</Ui> (X), or <Ui>Fix (request a new file)</Ui>{" "}
            (stays C). Enter a reason, click <Ui>Save decision</Ui>. Name and time are recorded.
          </Step>
          <Step n={4} title="Download the report">
            <Ui>Download quality report (.xlsx)</Ui> to send to the client (list of wells to fix).
          </Step>
        </Steps>
        <h3>Checks</h3>
        <Table
          head={["Critical (fail → C)", "Warning (→ B)"]}
          rows={[
            ["T&D model pick up & slack off present", "Actual/T&D model ratio deviates from similar wells"],
            ["Plausible units (no ~1000× difference)", "Implausible jumps between points"],
            ["Plausible values (hookload > 0, torque ≥ 0)", "Exactly repeated values (copy-paste)"],
            ["Slack off ≤ rotating ≤ pick up", "Far fewer points than similar wells"],
            ["≥ 8 actual points within the T&D model depth range", "Torque ratio far from 1, depth order decreasing"],
            ["Section & type known, not a duplicate", ""],
          ]}
        />
        <Go to="/quality">Open Data Quality</Go>
      </>
    ),
  },
  {
    id: "train",
    group: "Step by step",
    title: "4. Freezing a dataset and training a model",
    summary: "Frozen dataset + locked blind test, then compare algorithms.",
    keywords: "model train freeze dataset algorithm xgboost random forest ridge svr mlp held active",
    body: (
      <>
        <Steps>
          <Step n={1} title="Models → Datasets → Freeze a new dataset">
            Takes all <b>Training Data</b> wells with status A/B (never Monitoring), saves a snapshot + hash. The first dataset
            locks ~20% of the wells as the blind test. (If none is frozen, the first training run freezes one automatically.)
          </Step>
          <Step n={2} title="Models → Train a model">
            Choose the <Ui>Dataset</Ui> (default: latest) and <Ui>Algorithm</Ui>: <i>Compare all</i> (Ridge, XGBoost, Random
            Forest, SVR; tick <Ui>Include MLP</Ui> if needed). Click <Ui>Train model</Ui>. About 3–5 minutes; the status updates
            automatically.
          </Step>
          <Step n={3} title="Check Model history">
            <b>Done + active</b> = used for predictions. <b>Held</b> = worse than the active model (not activated automatically;{" "}
            <Ui>Activate</Ui> manually if you are sure).
          </Step>
        </Steps>
        <Flow
          title="What happens in Train model"
          nodes={[
            { title: "Frozen dataset", desc: "blind wells set aside" },
            { title: "Feature group tests", desc: "kept if the error drops ≥ 1% (incl. DD Calibrate)" },
            { title: "All algorithms", desc: "validated per well (5 folds)" },
            { title: "Best per operation" },
            { title: "Learning curve, SHAP", desc: "band P10–P90" },
            { title: "Compare with active", desc: "active / held", tone: "out" },
          ]}
        />
        <Go to="/models">Open Models</Go>
      </>
    ),
  },
  {
    id: "model-report",
    group: "Step by step",
    title: "5. Reading the model report and the blind test",
    summary: "RMSE, 'ML closer', analysis tabs, blind test once.",
    keywords: "model report rmse mape r2 ml closer learning curve shap blind test section type depth",
    body: (
      <>
        <Steps>
          <Step n={1} title="Click Report in Model history">The main table per operation appears below.</Step>
          <Step n={2} title="Read the main table">
            <b>RMSE T&amp;D model → RMSE ML</b>: mean error (smaller is better), in kN / kN·m. <b>ML vs T&amp;D model</b>:
            improvement in percent. <b>ML closer</b>: share of points where ML is closer to actual than the T&amp;D model.{" "}
            <b>Within tolerance</b>: share of points with |error| &lt; 10 klbf (hookload) or &lt; 2 kft-lbf (torque), the
            client's acceptance criterion; tab <Ui>Prediction backtest</Ui> shows it for 300 / 600 / 1,000 ft ahead.
          </Step>
          <Step n={3} title="Use the analysis tabs">
            <Ui>Section × type</Ui> (yellow rows = fewer than 3 wells, less reliable), <Ui>Depth</Ui>, <Ui>By well</Ui>,{" "}
            <Ui>Worst points</Ui>, <Ui>Algorithms</Ui>, <Ui>Single vs combination</Ui>, <Ui>Learning curve</Ui> (falling = more
            wells help), <Ui>SHAP</Ui> (most influential features).
          </Step>
          <Step n={4} title="Run the blind test (once)">
            After choosing the final model, click <Ui>Run blind test</Ui>. The result is recorded as is and cannot be repeated.
          </Step>
          <Step n={5} title="Download for the client">
            <Ui>Report (.xlsx)</Ui> (all tables) and <Ui>PDF summary</Ui> (metrics, blind test, learning curve, SHAP).
          </Step>
        </Steps>
        <Tip>
          Cross-validation numbers are computed on wells the model did not see, and the blind test on wells locked from the start.
          If ML is not better for a combination, the report shows it as is.
        </Tip>
      </>
    ),
  },
  {
    id: "monitoring",
    group: "Step by step",
    title: "6. Monitoring a well (prediction only)",
    summary: "Upload a well to be drilled or being drilled; it is predicted but never used for training.",
    keywords: "monitoring new well prediction template upload promote to training separate",
    body: (
      <>
        <Steps>
          <Step n={1} title="Monitoring → select Well section and Well type">Required before uploading.</Step>
          <Step n={2} title="Download the monitoring template (optional)">Or use the original WellPlan file of that well.</Step>
          <Step n={3} title="Fill in Well Info, Drag, Torque (Survey if available)">
            Actual readings are optional: add the T&amp;D Actual Reading sheet with the readings so far to predict ahead of the
            current depth.
          </Step>
          <Step n={4} title="Upload one file">The system imports, checks and predicts with the active model.</Step>
          <Step n={5} title="Read the result">
            Per operation at the final depth: T&amp;D model (OHFF 0.3), <b>ML prediction</b>, uncertainty band (P10–P90), ML − T&amp;D
            model. Buttons <Ui>Open dashboard</Ui>, <Ui>⬇ Prediction (.xlsx)</Ui>, <Ui>⬇ Summary (PDF)</Ui>.
          </Step>
          <Step n={6} title="While drilling">
            Upload the file again with new actual readings (same name and section): it replaces the previous version, and the
            stored prediction is evaluated automatically (Evaluations).
          </Step>
          <Step n={7} title="After the well is finished (optional)">
            <Ui>Promote to training</Ui> copies the well into Training Data. The copy goes through the data quality gate and is
            used in the next training run if it gets A/B.
          </Step>
        </Steps>
        <Tip kind="warn">
          Monitoring data never enters a dataset, even with complete actual data. Read the warnings: a section/type rare in the
          training data, depths outside the training range, or a missing survey make the prediction less reliable.
        </Tip>
        <Go to="/monitoring">Open Monitoring</Go>
      </>
    ),
  },
  {
    id: "dashboard",
    group: "Step by step",
    title: "7. Reading the dashboard",
    summary: "Standard plot labels, one colour per OHFF, band, limits, Difference, zoom.",
    keywords: "dashboard chart hookload torque difference zoom band ohff colour pu so rot calibrated interval threshold",
    body: (
      <>
        <Steps>
          <Step n={1} title="Select a well">
            Filter by <Ui>Data group</Ui>, <Ui>Well section</Ui>, <Ui>Well type</Ui>, <Ui>Quality</Ui>, then choose{" "}
            <Ui>Well</Ui>. <Ui>Units</Ui>: imperial (ft, klbf, ft-lbf) or SI. <Ui>Model</Ui>: active or another version.
          </Step>
          <Step n={2} title="WellPlan curves: with DD Calibrate or as modelled">
            <Ui>Automatic</Ui> shows the T&amp;D model <b>with the DD Calibrate offsets</b> when the file has them (the same
            curves as the Excel "Graph reference" crossplot), otherwise as modelled.
          </Step>
          <Step n={3} title="Read the Hookload and Torque panels">
            Y axis <b>Depth (ft)</b>. Curve names follow the client's Excel: <b>PU - OHFF : 0.3</b>, <b>SO - OHFF : 0.5</b>,{" "}
            <b>ROT</b> (one curve), <b>Torque On Bottom - OHFF : 0.3</b>, ML <b>PU - ML</b>, actual <b>PU Actual</b>. One fixed colour per OHFF in every chart:{" "}
            {Object.entries(OHFF_COLOR).map(([ff, c]) => (
              <span key={ff} className="nowrap">
                <Swatch c={c} /> {ff}{" "}
              </span>
            ))}
            . ML prediction <span style={{ color: "#eb6834" }}>orange</span>, uncertainty band (P10–P90) orange{" "}
            <b>dashed</b>, actual readings <span style={{ color: "#1baf7a" }}>green</span> points, operating limits red{" "}
            <b>dotted</b>.
          </Step>
          <Step n={4} title="Checkboxes">
            <Ui>All OHFF curves</Ui> (on by default) shows every OHFF; off = only OHFF 0.3. <Ui>Uncertainty band (P10–P90)</Ui>{" "}
            (off by default) adds the two dashed bounds.
          </Step>
          <Step n={5} title="Difference (Δ) panel">
            Δ = A − B. <b>Right (+) = A is higher</b>, left (−) = lower. Choose the target and <Ui>Absolute</Ui> /{" "}
            <Ui>Percent</Ui>.
          </Step>
          <Step n={6} title="Zoom">
            Drag a box on a chart; double click to go back; <Ui>Reset zoom</Ui> for all panels. With{" "}
            <Ui>Same depth in all panels when zooming</Ui> the panels follow each other. Hover: a guide line appears in all
            panels and the values show in the bar below.
          </Step>
          <Step n={7} title="Flag intervals">
            Choose the series and the |Δ| threshold in <Ui>Flag intervals</Ui>; intervals above the threshold are shaded yellow
            and listed below the charts with the 5 largest differences.
          </Step>
        </Steps>
        <Tip>
          For wells used in training, the ML line is an <b>unseen-well validation</b> prediction (from a model that never saw that
          well), so the comparison with actual data stays fair.
        </Tip>
        <Go to="/dashboard">Open Dashboard</Go>
      </>
    ),
  },
  {
    id: "forecast",
    group: "Step by step",
    title: "8. Prediction N ft ahead with cause and effect",
    summary: "Prediction the next 300 ft (or any distance) from the last actual depth, with explanations.",
    keywords: "prediction ahead distance 300 ft cause effect shap inclination dogleg interval limit bias correction export",
    body: (
      <>
        <Steps>
          <Step n={1} title="Dashboard → select the well → Prediction ahead">
            Enter <Ui>Distance</Ui> (e.g. 300 ft). <Ui>From depth</Ui> is optional; default = the last actual depth (or the top
            of the T&amp;D model when there is no actual data yet).
          </Step>
          <Step n={2} title="Local bias correction (on by default when the well has actual readings)">
            Shifts the prediction by the median (actual − ML) of the last 10 actual points within 1,000 ft. For display only; the
            model is not changed. It is the most accurate option in the backtest.
          </Step>
          <Step n={3} title="Click Run prediction">
            The prediction window is shaded in the charts. The table shows per operation: ML at the start and the end, the change,
            P10–P90 at the end, the <b>expected accuracy</b> (backtest of the active model for this distance on unseen wells:
            share of points within &lt; 10 klbf hookload / &lt; 2 kft-lbf torque) and the main drivers.
          </Step>
          <Step n={4} title="Read the cause and effect">
            One sentence per operation, e.g. <i>"Pick up: from 8,450 to 8,750 ft the ML prediction is expected to rise from 210.3
            to 225.1 klbf (+14.8). Main drivers: T&amp;D model (+10.2), Inclination (+3.1), inclination 28° → 34°. The max
            operating limit (250.0 klbf) is reached by the P10–P90 band at 8,720 ft."</i>
          </Step>
          <Step n={5} title="Export">
            <Ui>⬇ Prediction (.xlsx)</Ui>: Summary (sentences), one sheet per operation (depth, ML, P10, P90, T&amp;D model per OHFF
            and a chart), Explanation (drivers, plan changes, operating limits).
          </Step>
        </Steps>
        <h3>How the explanation is made</h3>
        <Table
          head={["Part", "Source"]}
          rows={[
            ["Main drivers", "Local SHAP: change of each feature's contribution between the start and the end of the window (feature swap for SVR/MLP). 'T&D model' = change of the T&D model curve itself."],
            ["Plan changes", "Survey: inclination at the start and the end, maximum dogleg, interval type (vertical / build / tangent / drop / horizontal)."],
            ["Operating limits", "First depth where the ML prediction or the P10–P90 band reaches a limit."],
          ]}
        />
        <Tip kind="warn">
          The ML needs the T&amp;D model as input: the prediction stops where the WellPlan results end (a warning says so).
        </Tip>
      </>
    ),
  },
  {
    id: "limits",
    group: "Step by step",
    title: "9. Operating limits",
    summary: "Set hookload/torque limits and see the depth where they are reached.",
    keywords: "operating limits limit torque top drive hookload slack off minimum depth margin",
    body: (
      <>
        <Steps>
          <Step n={1} title="Dashboard → Operating limits">Below the charts.</Step>
          <Step n={2} title="Add a limit">
            Choose the operation (pick up max, slack off min, torque on bottom max, …), enter the value in the display unit,
            choose <i>all wells in this section</i> or <i>this well only</i>, click <Ui>Add limit</Ui>.
          </Step>
          <Step n={3} title="Read the result">
            Table: first depth where ML, the ML band bound, and the T&amp;D model reach the limit (<i>not reached</i> = never),
            and the minimum margin. In the charts: a red dotted line at the limit and red shading below the ML crossing depth.
          </Step>
        </Steps>
        <Tip>A well limit overrides the section limit for the same operation. Limits are included in the Excel and PDF.</Tip>
      </>
    ),
  },
  {
    id: "export",
    group: "Step by step",
    title: "10. Excel and PDF output",
    summary: "Per-well results, prediction, model report, quality report.",
    keywords: "export excel pdf download report result prediction",
    body: (
      <>
        <Steps>
          <Step n={1} title="Dashboard → Export Excel">
            Sheets as the client's "OUTPUT … Multiple T&D Road Map" file: <b>Summary Outputs</b> (Actual vs Machine Learning table, drag/torque performance metrics, parity charts), <b>Tripping Load Analysis - Graph</b> (modelled hookloads per OHFF, actual hookloads, tripping data, ML prediction + chart), <b>Torque Analysis Off Btm</b> and <b>On Bottom</b> (modelled torque per OHFF, actual torque, ML + chart), and <b>ROT / SO / PU MW &lt;mud weight&gt;</b> (WellPlan multipoint outputs: header, BHA &amp; wellbore data, drilling parameters, per-OHFF table).
          </Step>
          <Step n={2} title="Dashboard → PDF">
            Summary: data quality, model & dataset versions, metrics, operating limits, six chart panels.
          </Step>
          <Step n={3} title="Dashboard → ⬇ Prediction (.xlsx)">Prediction N ft ahead with cause and effect.</Step>
          <Step n={4} title="Models → Report (.xlsx) / PDF summary">Model accuracy report for the client.</Step>
          <Step n={5} title="Data Quality → Download quality report (.xlsx)">Status of every well and the reasons.</Step>
        </Steps>
        <Tip>The Difference chart in Excel follows the target selected in the Difference panel when you click Export.</Tip>
      </>
    ),
  },
  {
    id: "evaluation",
    group: "Step by step",
    title: "11. Evaluation after drilling",
    summary: "Earlier predictions are compared with the actual data automatically.",
    keywords: "evaluation prediction actual after drilling comparison accuracy",
    body: (
      <>
        <Steps>
          <Step n={1} title="The well was predicted">Through Monitoring (before or while drilling).</Step>
          <Step n={2} title="Upload the file with its actual data">
            In <Ui>Monitoring</Ui>, with the same well name and section.
          </Step>
          <Step n={3} title="Open Evaluations">
            Per operation: RMSE T&amp;D model vs ML against actual, and the share of points where ML is closer.
          </Step>
        </Steps>
        <Go to="/evaluations">Open Evaluations</Go>
      </>
    ),
  },

  // ------------------------------------------------------------------ Use cases
  {
    id: "uc-onboarding",
    group: "Use cases",
    title: "UC-1 · Starting with 40+ wells",
    summary: "From the client's data folder to the first model and report.",
    keywords: "use case onboarding first 40 wells first time",
    body: (
      <>
        <p>
          <b>Actors:</b> engineer + operator. <b>Goal:</b> first model and an accuracy report for the client.
        </p>
        <Flow
          nodes={[
            { title: "Copy data to inbox", desc: "make inbox-training", tone: "user" },
            { title: "Scan folder", tone: "user", to: "/training" },
            { title: "Review status C", tone: "user", to: "/quality" },
            { title: "Freeze dataset v1", desc: "blind test locked", tone: "user", to: "/models" },
            { title: "Train: compare all", tone: "system" },
            { title: "Run blind test", tone: "user" },
            { title: "Model + quality reports", tone: "out" },
          ]}
        />
        <Steps>
          <Step n={1} title="Scan folder">Make sure no file is rejected; if one is, read the reason.</Step>
          <Step n={2} title="Data Quality">For each status C: accept / exclude / fix with a reason.</Step>
          <Step n={3} title="Models">Freeze the dataset, train (Compare all), read the report, run the blind test.</Step>
          <Step n={4} title="Send to the client">Quality report (.xlsx), model report (.xlsx + PDF).</Step>
        </Steps>
      </>
    ),
  },
  {
    id: "uc-add",
    group: "Use cases",
    title: "UC-2 · Adding wells and retraining",
    summary: "New drilled wells come in and the model is updated safely.",
    keywords: "use case add data retrain new version held promote",
    body: (
      <>
        <Steps>
          <Step n={1} title="Add the data">
            Scan folder or upload in Training Data, or <Ui>Promote to training</Ui> a finished monitoring well.
          </Step>
          <Step n={2} title="Check data quality">Review status C of the new wells.</Step>
          <Step n={3} title="Models → Freeze a new dataset">The version goes up; the existing blind test wells stay locked.</Step>
          <Step n={4} title="Train with the new dataset">
            Better → activated automatically. Worse → <b>held</b>; the previous model stays in use.
          </Step>
        </Steps>
        <Tip>Every model records its dataset version, so earlier results can always be traced and compared.</Tip>
      </>
    ),
  },
  {
    id: "uc-monitor",
    group: "Use cases",
    title: "UC-3 · Monitoring a well while drilling",
    summary: "The engineer follows a well being drilled and predicts the next section of hole.",
    keywords: "use case monitoring while drilling prediction ahead operating limit torque",
    body: (
      <>
        <Flow
          nodes={[
            { title: "Monitoring upload", desc: "T&D model + actual so far", tone: "user", to: "/monitoring" },
            { title: "Prediction", tone: "system" },
            { title: "Prediction 300 ft ahead", desc: "cause and effect", tone: "user", to: "/dashboard" },
            { title: "Operating limits", tone: "user" },
            { title: "Excel / PDF to the team", tone: "out" },
          ]}
        />
        <Steps>
          <Step n={1} title="Monitoring">Select section and type, upload. Note the warnings.</Step>
          <Step n={2} title="Dashboard">Compare ML with the T&amp;D model (with DD Calibrate); turn on the P10–P90 band.</Step>
          <Step n={3} title="Prediction ahead">300 ft, optional bias correction. Read the drivers and the limit crossings.</Step>
          <Step n={4} title="Add operating limits">E.g. top drive torque. See where the upper band reaches the limit.</Step>
          <Step n={5} title="Repeat">Upload the file again after each new set of actual readings.</Step>
        </Steps>
      </>
    ),
  },
  {
    id: "uc-evaluate",
    group: "Use cases",
    title: "UC-4 · Evaluating after drilling",
    summary: "How accurate was the earlier prediction?",
    keywords: "use case evaluation post drilling prediction accuracy",
    body: (
      <Steps>
        <Step n={1} title="Upload the actual data of the prediction well">In Monitoring, same well name and section.</Step>
        <Step n={2} title="Open Evaluations">Compare RMSE T&amp;D model vs ML and the share of points where ML is closer.</Step>
        <Step n={3} title="Use it for training (optional)">
          <Ui>Promote to training</Ui>: if the copy gets A/B, it is used in the next training run (UC-2).
        </Step>
      </Steps>
    ),
  },
  {
    id: "uc-problems",
    group: "Use cases",
    title: "UC-5 · Rejected file or status C",
    summary: "Handling problem data and requesting fixes from the client.",
    keywords: "use case rejected failed status c fix file wrong unit few points",
    body: (
      <>
        <Table
          head={["Message", "Meaning", "Action"]}
          rows={[
            ["Unknown format", "Not a roadmap or a WellPlan report", "Use the template, or check the sheet names"],
            ["Selected section differs from the file", "The selection and the file name/content disagree", "Check the selection; the selected section is used"],
            ["Only N actual points (minimum 8)", "Too little actual data", "Accept with a note, or request complete data"],
            ["Possible wrong unit", "Values differ ~1000× from the T&D model", "Check the column units (kip vs lbf), fix the file"],
            ["Order SO ≤ ROT ≤ PU violated", "Columns swapped or misrecorded", "Check the columns; fix the file"],
            ["No actual data", "The file only has the T&D model", "Fine for Monitoring; Training needs actual data"],
          ]}
        />
        <Steps>
          <Step n={1} title="Data Quality → click the well → decision Fix">With a clear reason.</Step>
          <Step n={2} title="Download the quality report">Send the list of wells to fix to the client.</Step>
          <Step n={3} title="The fixed file arrives">Upload/scan again; the new version replaces the old one and quality is recomputed.</Step>
        </Steps>
      </>
    ),
  },

  // ------------------------------------------------------------------ System flow
  {
    id: "data-flow",
    group: "System flow",
    title: "Data flow: from file to prediction",
    summary: "What the system does behind the scenes at each stage.",
    keywords: "flow system process data parser import database dataset model prediction",
    body: (
      <>
        <Flow
          title="1. Data in"
          nodes={[
            { title: "Excel file", desc: "folder / upload / template", tone: "user" },
            { title: "Purpose + section + type", desc: "selected by the user", tone: "user" },
            { title: "Format detection", desc: "from sheet names" },
            { title: "Parser A / B", desc: "T&D model per OHFF, DD Calibrate, actual, survey" },
            { title: "Unit conversion", desc: "original + SI stored" },
            { title: "Database", desc: "Training or Monitoring", tone: "out" },
          ]}
        />
        <Flow
          title="2. Quality and dataset (Training Data only)"
          nodes={[
            { title: "Quality gate", desc: "9 critical + 5 statistical" },
            { title: "Status A/B/C", desc: "+ engineer review" },
            { title: "Pair actual ↔ T&D model", desc: "at the same depth" },
            { title: "Features", desc: "T&D model OHFF 0.3 & 0.5, survey, DD Calibrate, …" },
            { title: "Frozen dataset", desc: "hash + blind test", tone: "out" },
          ]}
        />
        <Flow
          title="3. Model and results"
          nodes={[
            { title: "Train & validate per well", desc: "5 folds" },
            { title: "Active model", desc: "or held" },
            { title: "Prediction", desc: "depth grid + P10–P90" },
            { title: "Prediction N ft ahead", desc: "cause and effect", tone: "out" },
            { title: "Dashboard / Excel / PDF / Evaluation", tone: "out" },
          ]}
        />
      </>
    ),
  },
  {
    id: "status-cycle",
    group: "System flow",
    title: "Status cycle: file, well, model",
    summary: "What each status means and how it changes.",
    keywords: "status cycle file accepted rejected replaced well a b c x model queued running done held failed active",
    body: (
      <>
        <h3>File</h3>
        <Flow
          nodes={[
            { title: "Processing" },
            { title: "OK / Warning", desc: "accepted", tone: "out" },
            { title: "Replaced", desc: "when a new version arrives" },
          ]}
        />
        <p className="small muted">
          Or <b>Failed</b> (rejected, with the reason). An identical file is not imported again (duplicate).
        </p>
        <h3>Well section</h3>
        <Flow
          nodes={[
            { title: "Imported" },
            { title: "Automatic checks" },
            { title: "A / B / C" },
            { title: "Review", desc: "accept → B, exclude → X, fix → C", tone: "user" },
            { title: "A/B Training wells enter the dataset", tone: "out" },
          ]}
        />
        <Table head={["Status", "Meaning", "Used for training?"]} rows={STATUS_ROWS} />
        <h3>Model</h3>
        <Flow
          nodes={[
            { title: "Queued" },
            { title: "Running" },
            { title: "Done + active", desc: "better / first", tone: "out" },
            { title: "or Held", desc: "worse than active" },
          ]}
        />
        <p className="small muted">
          <b>Failed</b>: the error is shown in Model history (e.g. fewer than 5 training wells). Blind test <b>done</b> = cannot
          be repeated.
        </p>
      </>
    ),
  },

  // ------------------------------------------------------------------ Reference
  {
    id: "outputs",
    group: "Reference",
    title: "System outputs",
    summary: "Every file/result you can get and where.",
    keywords: "output result report file download",
    body: (
      <Table
        head={["Output", "Where", "Content"]}
        rows={[
          ["Upload templates", "Training Data / Monitoring → step 2", "Training and monitoring templates (+ Instructions, Example)"],
          ["Folder scan result", "Training Data → Scan folder", "Status per file and per well section"],
          ["Data quality report (.xlsx)", "Data Quality", "Status A/B/C/X, score, reasons, reviews"],
          ["Frozen dataset (.csv.gz)", "Models → Datasets → Download", "Training data + hash, blind wells"],
          ["Model report (.xlsx / PDF)", "Models → Report", "Accuracy per operation/section/type/depth/well, blind test, learning curve, SHAP"],
          ["Monitoring prediction", "Monitoring → upload", "Summary table + Excel + PDF"],
          ["Dashboard", "Dashboard", "Charts, band, operating limits, flagged intervals"],
          ["Prediction N ft (.xlsx)", "Dashboard → Prediction ahead", "Prediction per depth, P10–P90, T&D model per OHFF, cause and effect"],
          ["Prediction Output (.xlsx) / PDF", "Dashboard → Export Excel / PDF", "Client format: Summary Outputs, Tripping Load & Torque graphs, PU/SO/ROT MW sheets"],
          ["Evaluation", "Evaluations", "Prediction vs actual after drilling"],
        ]}
      />
    ),
  },
  {
    id: "faq",
    group: "Reference",
    title: "FAQ and troubleshooting",
    summary: "Common questions.",
    keywords: "faq question problem error cannot why",
    body: (
      <Table
        head={["Question", "Answer"]}
        rows={[
          ["Do I have to use the template?", "No. Original WellPlan files (.xlsm report or .xlsx roadmap) can be uploaded directly. Always select the section and type first."],
          ["The upload area is greyed out", "Select the Well section and Well type first (step 1)."],
          ["Training or Monitoring?", "Drilled wells with actual data that should teach the ML → Training Data. A well being drilled → Monitoring."],
          ["Why does the T&D model curve differ from the raw WellPlan numbers?", "The dashboard adds the DD Calibrate offsets by default (as the Excel crossplot). Choose 'As modelled' under WellPlan curves to see the raw curves."],
          ["Scan folder is disabled", "The inbox folder is empty. The operator copies files to data/inbox."],
          ["A file is 'skipped' when scanning", "It was modified less than 1 minute ago. Wait and scan again."],
          ["Why is my well status C?", "Open Data Quality and click the well: the critical reason is listed. See UC-5."],
          ["A new model is 'held'", "Its accuracy is worse than the active model. The previous model stays in use; you can activate it manually."],
          ["Can the blind test be repeated?", "No, it runs once per model on purpose so the result is fair."],
          ["The ML line does not show", "The well has not been predicted: click Run prediction again on the dashboard, or no model is active yet."],
          ["Units", "Choose imperial (ft, klbf, ft-lbf) or SI (m, kN, kN·m) on the dashboard."],
          ["Sign-in is locked", "Wait 15 minutes, or the operator runs make password."],
        ]}
      />
    ),
  },
];
