// Centralized Gemini model configuration for the frontend
// Use stable model slugs to avoid frequent preview renames

export type ModelOption = {
  id: string; // Gemini model slug
  label: string; // Shown in the dropdown
};

// Recommended stable options
export const MODEL_OPTIONS: ModelOption[] = [
  { id: "gemini-2.5-flash-lite", label: "2.5 Flash-Lite" },
  { id: "gemini-2.5-flash", label: "2.5 Flash" },
  { id: "gemini-2.5-pro", label: "2.5 Pro" },
];

// Default reasoning model for reflection/finalization
export const DEFAULT_REASONING_MODEL = "gemini-2.5-flash-lite";

// Default effort level for new searches
export const DEFAULT_EFFORT = "low";

// Default placeholder text
export const DEFAULT_PLACEHOLDER = "Who won the Euro 2024 and scored the most goals?";
