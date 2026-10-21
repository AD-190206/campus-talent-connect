import { ArrowRight, BadgeCheck, CalendarDays, CircleCheck, FileText, Search, ShieldCheck, Wallet } from "lucide-react";
import { Logo, ThemeToggle } from "@/components/brand";
import { ButtonLink } from "@/components/ui/button";
import { LandingAuthActions, LatestProjects } from "./landing-client";

const STUDENT_STEPS = [
  { title: "Create your profile", text: "Add your college, skills and portfolio links." },
  { title: "Find a project", text: "Search open projects by keyword, skill, category or budget." },
  { title: "Send a proposal", text: "Explain your approach and track every application’s status." },
  { title: "Deliver and get paid", text: "Submit work, respond to feedback, and receive payment on approval." },
];

const CLIENT_STEPS = [
  { title: "Post a project", text: "Describe the work, required skills, budget and deadline." },
  { title: "Review applicants", text: "Read proposals, shortlist, and select one student." },
  { title: "Fund the assignment", text: "The payment amount is fixed to the project’s published budget." },
  { title: "Approve the work", text: "Request revisions or approve; payment is released on approval." },
];

const BENEFITS = [
  {
    icon: BadgeCheck,
    title: "Real work, real portfolio",
    text: "Every completed assignment is a delivered project and a review you can point to.",
  },
  {
    icon: Wallet,
    title: "Clear payment rules",
    text: "Amounts come from the published budget and are released only after the client approves the work.",
  },
  {
    icon: ShieldCheck,
    title: "Simple, accountable process",
    text: "Applications, deliverables and reviews follow one tracked workflow, start to finish.",
  },
];

function ProjectPreview() {
  return (
    <div className="relative mx-auto w-full max-w-md sm:mb-32" aria-label="Example project listing" role="img">
      <div className="card p-5 shadow-pop">
        <div className="flex items-center justify-between">
          <span className="inline-flex h-6 items-center gap-1 rounded-md bg-accent px-2 text-xs font-medium text-accent-fg">
            <span className="h-1.5 w-1.5 rounded-full bg-current" /> Open
          </span>
          <span className="text-xs text-muted">Example listing</span>
        </div>
        <p className="mt-4 text-[15px] font-semibold">Landing page for a campus café</p>
        <p className="mt-1.5 text-sm leading-relaxed text-muted">
          Design and build a responsive one-page site with a menu, opening hours and a contact form.
        </p>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {["React", "Tailwind", "Figma"].map((s) => (
            <span key={s} className="inline-flex h-6 items-center rounded-md border border-line px-2 text-xs text-muted">
              {s}
            </span>
          ))}
        </div>
        <div className="mt-5 flex items-center justify-between border-t border-line pt-4 text-sm">
          <span className="font-semibold">₹8,000</span>
          <span className="inline-flex items-center gap-1.5 text-muted">
            <CalendarDays className="h-3.5 w-3.5" /> 3 weeks
          </span>
        </div>
      </div>
      <div className="card absolute -bottom-32 -left-4 hidden w-56 p-4 shadow-pop sm:block lg:-left-12">
        <p className="label-caps">Your application</p>
        <ol className="mt-3 space-y-2.5 text-[13px]">
          {[
            ["Submitted", true],
            ["Shortlisted", true],
            ["Selected", false],
          ].map(([label, done]) => (
            <li key={label as string} className="flex items-center gap-2">
              <CircleCheck className={done ? "h-4 w-4 text-success" : "h-4 w-4 text-line-strong"} />
              <span className={done ? "text-fg" : "text-muted"}>{label}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function Steps({ title, icon: Icon, steps }: { title: string; icon: typeof Search; steps: typeof STUDENT_STEPS }) {
  return (
    <div className="card p-6 sm:p-8">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-fg">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <h3 className="text-base font-semibold">{title}</h3>
      </div>
      <ol className="mt-6 space-y-5">
        {steps.map((step, i) => (
          <li key={step.title} className="flex gap-4">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line text-xs font-medium tabular-nums text-muted">
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-medium">{step.title}</p>
              <p className="mt-0.5 text-sm text-muted">{step.text}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-transparent bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          {/* Mark only on narrow screens so the header never overflows. */}
          <span className="sm:hidden">
            <Logo compact />
          </span>
          <span className="hidden sm:block">
            <Logo />
          </span>
          <nav aria-label="Primary" className="hidden items-center gap-6 text-sm text-muted md:flex">
            <a href="#how-it-works" className="hover:text-fg">
              How it works
            </a>
            <a href="#benefits" className="hover:text-fg">
              Why CTC
            </a>
          </nav>
          <div className="flex items-center gap-1.5">
            <ThemeToggle />
            <LandingAuthActions />
          </div>
        </div>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-16 px-4 pb-20 pt-14 sm:px-6 lg:grid-cols-[1.1fr_1fr] lg:pb-28 lg:pt-24">
          <div>
            <p className="label-caps">For students and the people who hire them</p>
            <h1 className="mt-4 max-w-xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
              Your skills deserve real-world opportunities.
            </h1>
            <p className="mt-5 max-w-lg text-base leading-relaxed text-muted sm:text-lg">
              Discover meaningful projects, build your portfolio, and work with clients who value emerging talent.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <ButtonLink href="/projects" size="lg">
                Explore Projects
                <ArrowRight className="h-4 w-4" aria-hidden />
              </ButtonLink>
              <ButtonLink href="/register?role=client" size="lg" variant="secondary">
                Hire Student Talent
              </ButtonLink>
            </div>
          </div>
          <ProjectPreview />
        </section>

        <LatestProjects />

        <section id="how-it-works" className="border-t border-line bg-surface-2/50">
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <p className="label-caps">How it works</p>
            <h2 className="mt-3 max-w-xl text-2xl font-semibold tracking-tight sm:text-3xl">
              One clear workflow, from first proposal to final payment.
            </h2>
            <div className="mt-10 grid gap-5 lg:grid-cols-2">
              <Steps title="For students" icon={Search} steps={STUDENT_STEPS} />
              <Steps title="For clients" icon={FileText} steps={CLIENT_STEPS} />
            </div>
          </div>
        </section>

        <section id="benefits" className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <div className="grid gap-10 md:grid-cols-3">
            {BENEFITS.map(({ icon: Icon, title, text }) => (
              <div key={title}>
                <Icon className="h-5 w-5 text-primary" aria-hidden />
                <h3 className="mt-4 text-base font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
          <div className="flex flex-col items-start justify-between gap-6 rounded-2xl bg-primary px-6 py-10 text-on-primary sm:px-10 md:flex-row md:items-center">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Start with one project.</h2>
              <p className="mt-2 max-w-md text-sm opacity-80">
                Create a free account as a student or a client. It takes less than a minute.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <ButtonLink href="/register" size="lg" variant="inverse">
                Get started
              </ButtonLink>
              <ButtonLink href="/login" size="lg" variant="inverse-ghost">
                Sign in
              </ButtonLink>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <Logo />
          <p>A student freelancing platform · College project prototype</p>
        </div>
      </footer>
    </div>
  );
}
