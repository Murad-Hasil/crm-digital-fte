"use client";

import { useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Category = "general" | "technical" | "billing" | "feedback" | "bug_report";
type Priority = "low" | "medium" | "high";
type Status = "idle" | "submitting" | "success" | "error";

interface FormData {
  name: string;
  email: string;
  subject: string;
  category: Category;
  priority: Priority;
  message: string;
}

interface FieldError {
  name?: string;
  email?: string;
  subject?: string;
  message?: string;
}

interface ApiResponse {
  ticket_id: string;
  message: string;
  estimated_response_time: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "general",    label: "General Question" },
  { value: "technical",  label: "Technical Support" },
  { value: "billing",    label: "Billing Inquiry" },
  { value: "bug_report", label: "Bug Report" },
  { value: "feedback",   label: "Feedback" },
];

const PRIORITIES: { value: Priority; label: string; color: string }[] = [
  { value: "low",    label: "Low — Not urgent",       color: "text-emerald-400" },
  { value: "medium", label: "Medium — Need help soon", color: "text-amber-400" },
  { value: "high",   label: "High — Urgent issue",    color: "text-rose-400" },
];

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validate(data: FormData): FieldError {
  const errors: FieldError = {};
  if (data.name.trim().length < 2)
    errors.name = "Name must be at least 2 characters.";
  if (!EMAIL_RE.test(data.email))
    errors.email = "Please enter a valid email address.";
  if (data.subject.trim().length < 5)
    errors.subject = "Subject must be at least 5 characters.";
  if (data.message.trim().length < 10)
    errors.message = "Please describe your issue in more detail (min 10 characters).";
  return errors;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function InputField({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-300">
        {label} <span className="text-rose-400">*</span>
      </label>
      {children}
      {error && (
        <p className="text-xs text-rose-400 animate-fade-in">{error}</p>
      )}
    </div>
  );
}

function GlassInput({
  id,
  type = "text",
  value,
  onChange,
  placeholder,
  hasError,
}: {
  id: string;
  type?: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  hasError?: boolean;
}) {
  return (
    <input
      id={id}
      name={id}
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      required
      className={`
        w-full rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500
        bg-white/5 border backdrop-blur-sm outline-none transition-all duration-200
        focus:bg-white/10 focus:border-violet-500 focus:ring-1 focus:ring-violet-500/50
        ${hasError ? "border-rose-500/70" : "border-white/10"}
      `}
    />
  );
}

function GlassSelect({
  id,
  value,
  onChange,
  options,
}: {
  id: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      id={id}
      name={id}
      value={value}
      onChange={onChange}
      className="
        w-full rounded-xl px-4 py-3 text-sm text-white
        bg-white/5 border border-white/10 backdrop-blur-sm outline-none
        transition-all duration-200 cursor-pointer appearance-none
        focus:bg-white/10 focus:border-violet-500 focus:ring-1 focus:ring-violet-500/50
      "
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value} className="bg-slate-900">
          {opt.label}
        </option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Success screen
// ---------------------------------------------------------------------------

function SuccessScreen({
  response,
  onReset,
}: {
  response: ApiResponse;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-6 py-6 animate-slide-up text-center">
      {/* Animated check */}
      <div className="flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/20 ring-2 ring-emerald-500/40">
        <svg
          className="h-10 w-10 text-emerald-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>

      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-white">Request Submitted!</h2>
        <p className="text-slate-400 text-sm">{response.message}</p>
      </div>

      {/* Ticket ID badge */}
      <div className="w-full rounded-2xl bg-white/5 border border-white/10 p-4 backdrop-blur-sm">
        <p className="text-xs text-slate-500 mb-1">Your Ticket ID</p>
        <p className="font-mono text-lg font-semibold text-violet-300 break-all">
          {response.ticket_id}
        </p>
        <p className="text-xs text-slate-500 mt-2">
          {response.estimated_response_time}
        </p>
      </div>

      <p className="text-xs text-slate-500 max-w-xs">
        Our AI assistant will respond to your email shortly. Urgent issues are
        prioritised automatically.
      </p>

      <button
        onClick={onReset}
        className="
          w-full rounded-xl py-3 px-6 text-sm font-semibold text-white
          bg-gradient-to-r from-violet-600 to-indigo-600
          hover:from-violet-500 hover:to-indigo-500
          transition-all duration-200 active:scale-[0.98]
        "
      >
        Submit Another Request
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const INITIAL_FORM: FormData = {
  name: "",
  email: "",
  subject: "",
  category: "general",
  priority: "medium",
  message: "",
};

export default function SupportForm({
  apiEndpoint = `${API_URL}/webhooks/webform`,
}: {
  apiEndpoint?: string;
}) {
  const [form, setForm] = useState<FormData>(INITIAL_FORM);
  const [errors, setErrors] = useState<FieldError>({});
  const [status, setStatus] = useState<Status>("idle");
  const [apiResponse, setApiResponse] = useState<ApiResponse | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
    // Clear inline error as the user types
    if (errors[name as keyof FieldError]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setApiError(null);

    const fieldErrors = validate(form);
    if (Object.keys(fieldErrors).length > 0) {
      setErrors(fieldErrors);
      return;
    }

    setStatus("submitting");
    try {
      const res = await fetch(apiEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Server error ${res.status}`);
      }

      const data: ApiResponse = await res.json();
      setApiResponse(data);
      setStatus("success");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Submission failed. Please try again.");
      setStatus("error");
    }
  }

  function handleReset() {
    setForm(INITIAL_FORM);
    setErrors({});
    setApiResponse(null);
    setApiError(null);
    setStatus("idle");
  }

  const isSubmitting = status === "submitting";

  return (
    // Glass card
    <div
      className="
        w-full max-w-lg rounded-3xl p-8
        bg-white/5 border border-white/10
        backdrop-blur-xl shadow-2xl shadow-black/40
        animate-fade-in
      "
    >
      {/* Header */}
      <div className="mb-8 flex flex-col gap-1">
        <div className="flex items-center gap-3 mb-1">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-600/30 ring-1 ring-violet-500/40 text-lg">
            🎧
          </span>
          <h1 className="text-2xl font-bold text-white">CloudScale AI Support</h1>
        </div>
        <p className="text-sm text-slate-400">
          CloudScale AI assistant will respond within 5 minutes.
        </p>
      </div>

      {/* Success screen */}
      {status === "success" && apiResponse ? (
        <SuccessScreen response={apiResponse} onReset={handleReset} />
      ) : (
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">

          {/* Global API error */}
          {apiError && (
            <div className="rounded-xl bg-rose-500/10 border border-rose-500/30 px-4 py-3 text-sm text-rose-300 animate-fade-in">
              {apiError}
            </div>
          )}

          {/* Name */}
          <InputField id="name" label="Your Name" error={errors.name}>
            <GlassInput
              id="name"
              value={form.name}
              onChange={handleChange}
              placeholder="Jane Doe"
              hasError={!!errors.name}
            />
          </InputField>

          {/* Email */}
          <InputField id="email" label="Email Address" error={errors.email}>
            <GlassInput
              id="email"
              type="email"
              value={form.email}
              onChange={handleChange}
              placeholder="jane@example.com"
              hasError={!!errors.email}
            />
          </InputField>

          {/* Subject */}
          <InputField id="subject" label="Subject" error={errors.subject}>
            <GlassInput
              id="subject"
              value={form.subject}
              onChange={handleChange}
              placeholder="Brief description of your issue"
              hasError={!!errors.subject}
            />
          </InputField>

          {/* Category + Priority row */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label htmlFor="category" className="text-sm font-medium text-slate-300">
                Category <span className="text-rose-400">*</span>
              </label>
              <GlassSelect
                id="category"
                value={form.category}
                onChange={handleChange}
                options={CATEGORIES}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="priority" className="text-sm font-medium text-slate-300">
                Priority
              </label>
              <GlassSelect
                id="priority"
                value={form.priority}
                onChange={handleChange}
                options={PRIORITIES}
              />
            </div>
          </div>

          {/* Message */}
          <InputField id="message" label="How can we help?" error={errors.message}>
            <div className="relative">
              <textarea
                id="message"
                name="message"
                value={form.message}
                onChange={handleChange}
                rows={5}
                placeholder="Please describe your issue or question in detail..."
                required
                className={`
                  w-full rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500
                  bg-white/5 border backdrop-blur-sm outline-none transition-all duration-200
                  resize-none focus:bg-white/10 focus:border-violet-500 focus:ring-1
                  focus:ring-violet-500/50
                  ${errors.message ? "border-rose-500/70" : "border-white/10"}
                `}
              />
              <span
                className={`
                  absolute bottom-3 right-3 text-xs
                  ${form.message.length < 10 ? "text-rose-400" : "text-slate-500"}
                `}
              >
                {form.message.length}/1000
              </span>
            </div>
          </InputField>

          {/* Submit */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="
              relative w-full rounded-xl py-3.5 px-6 text-sm font-semibold text-white
              bg-gradient-to-r from-violet-600 to-indigo-600
              hover:from-violet-500 hover:to-indigo-500 disabled:opacity-60
              disabled:cursor-not-allowed transition-all duration-200 active:scale-[0.98]
              focus:outline-none focus:ring-2 focus:ring-violet-500/50
            "
          >
            {isSubmitting ? (
              <span className="flex items-center justify-center gap-2">
                <svg
                  className="h-4 w-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12" cy="12" r="10"
                    stroke="currentColor" strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v8H4z"
                  />
                </svg>
                Submitting…
              </span>
            ) : (
              "Submit Support Request"
            )}
          </button>

          <p className="text-center text-xs text-slate-600">
            By submitting, you agree to our{" "}
            <a href="/privacy" className="text-violet-400 hover:underline">
              Privacy Policy
            </a>
            .
          </p>
        </form>
      )}
    </div>
  );
}
