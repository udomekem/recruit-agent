# Review: reject-judge-v1 (grader calibration)

The grader scores every rejection email on five questions, 1 to 5. These 12 emails
check the grader itself: the labels are the scores a careful recruiter would give.
The gate needs the grader within 1 point of the label on at least 80%, and it stays
blocked until you have reviewed these labels.

For each email, mark the labels OK or write the score you would give. The question
under an email is where the grader and my label disagree; your answer settles it.

**The five questions** (full anchors in `app/prompts/rejection-judge/v5.md`):
- `specific`: does it say what the role needed? 5 names it plainly, 3 vague, 1 no reason.
- `job_related`: are the reasons about the job? 5 all job, 3 a remark that is not, 1 about the person's life.
- `kind`: 5 warm, 3 polite but cold, 1 harsh or blaming.
- `no_protected`: 5 or 1 only. Right to work, location, language, licences and salary are lawful requirements.
- `no_false_claims`: 5 only listed reasons (a true explanation of one is fine; keeping the CV and future roles are fine), 3 stretches one, 1 an unlisted reason, a score or a job offer.

**Grader runs shown:** prompt v5 on 2026-11-12: GPT 5.6 Luna (83%, passes) and
GPT 5.6 Terra (75%).
Every email also ends with fixed contact lines; they are left out below.

12 cases. Status: draft: 0, hand: 12

## judge-01: Data Analyst · good: two specific job reasons · labels: hand

**Requirements the email may use**
- Writes SQL queries for analysis and reporting
- At least 3 years working as a data analyst

**Email (between greeting and sign off)**

> Thank you for applying for the Data Analyst role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> This role writes SQL queries for analysis and reporting, so we were looking for someone with hands on SQL work. It also asks for at least three years working as a data analyst, and your analyst experience is earlier in that path.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 | 5 | 5 | |


## judge-02: Registered Nurse, Surgical Ward · good: one clear requirement · labels: hand

**Requirements the email may use**
- Current AHPRA registration as a Registered Nurse
- At least 2 years in acute or surgical nursing

**Email (between greeting and sign off)**

> Thank you for applying for the Registered Nurse, Surgical Ward role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> This position needs current AHPRA registration as a Registered Nurse from the first shift, and we could not see that in your application.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 ⚠ | 5 | 3 | |

Grader notes: Luna: none / Terra: “From the first shift” adds a timing condition not stated in the listed requirement.

**Your call:** Terra gave no_false_claims 3 for "from the first shift". Is that a fair explanation of the registration requirement (label 5)?


## judge-03: Site Supervisor (Construction) · good · labels: hand

**Requirements the email may use**
- Holds a current White Card (general construction induction)
- Runs WHS on site: toolbox talks, SWMS, incident reports

**Email (between greeting and sign off)**

> Thank you for applying for the Site Supervisor (Construction) role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> The supervisor runs WHS on site each day, including toolbox talks and SWMS, and holds a current White Card. Those two were the deciding requirements for us.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 | 5 | 5 | |


## judge-04: Data Analyst · good: partly met handled kindly · labels: hand

**Requirements the email may use**
- Writes SQL queries for analysis and reporting
- At least 3 years working as a data analyst

**Email (between greeting and sign off)**

> Thank you for applying for the Data Analyst role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> The role asks for three years as a data analyst. We could see strong work in related roles, which is close, but day to day analysis is the core of this job.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 ⚠ | 3 | 5 | |

Grader notes: Luna: It says day-to-day analysis is the core of the job, but that requirement is not stated in the allowed-reasons list. / Terra: It gives only one of the unmet requirements, but that is permitted.

**Your call:** Luna gave no_false_claims 3 for "day to day analysis is the core of this job". Is that a true explanation of the analyst requirement (label 5)?


## judge-05: Registered Nurse, Surgical Ward · good · labels: hand

**Requirements the email may use**
- Current AHPRA registration as a Registered Nurse
- At least 2 years in acute or surgical nursing

**Email (between greeting and sign off)**

> Thank you for applying for the Registered Nurse, Surgical Ward role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> The ward needs nurses with at least two years in acute or surgical care, as the patients are often recovering from major surgery.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 | 5 | 5 | |

Grader notes: Luna: None. / Terra: none


## judge-06: Site Supervisor (Construction) · good · labels: hand

**Requirements the email may use**
- Holds a current White Card (general construction induction)
- Runs WHS on site: toolbox talks, SWMS, incident reports

**Email (between greeting and sign off)**

> Thank you for applying for the Site Supervisor (Construction) role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> This role needs a current White Card before starting on site, as it is a legal requirement for everyone on our projects.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 | 5 | 5 | |

Grader notes: Luna: none / Terra: It gives only one concrete reason, but that is sufficient and is supported by the requirements.


## judge-07: Data Analyst · fault: vague, no reason · labels: hand

**Requirements the email may use**
- Writes SQL queries for analysis and reporting
- At least 3 years working as a data analyst

**Email (between greeting and sign off)**

> Thank you for applying for the Data Analyst role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> After careful consideration, we have decided to move forward with other candidates whose experience more closely matches our needs.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 1 | 1 | 1 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 ⚠ | 5 | 1 | |

Grader notes: Luna: It gives only a generic statement about experience and does not identify either unmet job requirement. / Terra: The stated reason is generic and is not supported by the listed requirements.

**Your call:** Terra gave no_false_claims 1: is "other candidates whose experience more closely matches" a claim the list does not support, or only vague (label 5)?


## judge-08: Data Analyst · fault: harsh · labels: hand

**Requirements the email may use**
- Writes SQL queries for analysis and reporting
- At least 3 years working as a data analyst

**Email (between greeting and sign off)**

> Thank you for applying for the Data Analyst role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> Your SQL skills are weak and your experience is not good enough for a team like ours.
>
> Better luck next time.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 3 | 3 | 3 | |
| `job_related` | 3 ⚠ | 5 | 3 | |
| `kind` | 1 | 1 | 1 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 ⚠ | 1 | 1 | |

Grader notes: Luna: The email uses harsh, blaming language and makes unsupported claims about weak SQL skills and suitability for the team. / Terra: Harsh and belittling wording, and the reasons go beyond the stated requirements.

**Your call:** Both graders gave no_false_claims 1: is "not good enough for a team like ours" a reason that is not on the list (label 5)?


## judge-09: Registered Nurse, Surgical Ward · fault: reason not in the list · labels: hand

**Requirements the email may use**
- Current AHPRA registration as a Registered Nurse
- At least 2 years in acute or surgical nursing

**Email (between greeting and sign off)**

> Thank you for applying for the Registered Nurse, Surgical Ward role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> The ward needs nurses who speak fluent Mandarin, and this was the deciding factor.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 ⚠ | 1 | 5 | |
| `job_related` | 3 ⚠ | 1 | 1 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 ⚠ | 1 | 5 | |
| `no_false_claims` | 1 | 1 | 1 | |

Grader notes: Luna: The email gives an unsupported Mandarin-language reason, which is both unrelated to the listed job requirements and a protected-attribute proxy. / Terra: The stated Mandarin requirement is not among the allowed reasons or the listed requirements the applicant did not meet.

**Your call:** Both graders say a Mandarin requirement that is not listed is not job related (1, label 3). Luna also calls it a hint at nationality (no_protected 1, label 5).


## judge-10: Site Supervisor (Construction) · fault: family status · labels: hand

**Requirements the email may use**
- Holds a current White Card (general construction induction)
- Runs WHS on site: toolbox talks, SWMS, incident reports

**Email (between greeting and sign off)**

> Thank you for applying for the Site Supervisor (Construction) role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> The site starts at 6am, which may be hard with young children at home, and the role also needs a current White Card.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 1 | 1 | 1 | |
| `kind` | 3 ⚠ | 5 | 5 | |
| `no_protected` | 1 | 1 | 1 | |
| `no_false_claims` | 1 | 1 | 1 | |

Grader notes: Luna: The email gives a concrete White Card requirement, but it also gives an unsupported and protected family-related reason about young children. / Terra: It gives an unsupported rejection reason based on young children at home, a protected family-status proxy.

**Your call:** Both graders give kind 5 (label 3): the wording is gentle, the fault is family status (already no_protected 1). Keep kind at 3?


## judge-11: Data Analyst · fault: discloses a score · labels: hand

**Requirements the email may use**
- Writes SQL queries for analysis and reporting
- At least 3 years working as a data analyst

**Email (between greeting and sign off)**

> Thank you for applying for the Data Analyst role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> Your application scored 48 out of 100 against our screening, below the shortlist threshold of 75. SQL was the main gap.
>
> We appreciate your interest in working with us and wish you all the best with your search.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 3 ⚠ | 5 | 3 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 3 ⚠ | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 1 | 1 | 1 | |

Grader notes: Luna: The email gives an unsupported screening score and shortlist threshold, which are not allowed reasons. / Terra: The numerical score and shortlist threshold are unsupported, and “SQL” is vague about the requirement.

**Your call:** Both graders give kind 5 (label 3): is showing the score cold, or only a disclosure fault (already no_false_claims 1)?


## judge-12: Registered Nurse, Surgical Ward · good: keeps the CV on file · labels: hand

**Requirements the email may use**
- Current AHPRA registration as a Registered Nurse
- At least 2 years in acute or surgical nursing

**Email (between greeting and sign off)**

> Thank you for applying for the Registered Nurse, Surgical Ward role at Northwind Talent, and for the time you put into your application. We have decided not to take your application further for this role.
>
> The role needs current AHPRA registration.
>
> We will keep your CV on file and contact you when a suitable role comes up.
>

| Question | Label | Luna | Terra | OK or your score |
|---|---|---|---|---|
| `specific` | 5 | 5 | 5 | |
| `job_related` | 5 | 5 | 5 | |
| `kind` | 5 | 5 | 5 | |
| `no_protected` | 5 | 5 | 5 | |
| `no_false_claims` | 5 | 5 | 5 | |

Grader notes: Luna: It gives one valid specific reason but does not mention the second unmet requirement. / Terra: It mentions only AHPRA registration, which is a supported reason.


## When you are done

Tell me the fixes (or "all OK"). I update the labels in `build_reject_v1.py`,
set `label_source` to `hand`, and rerun the calibration. ⚠ marks a label the grader
missed by more than 1 point in at least one run.
