/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      colors: {
        ink: "#14213d",
        solar: "#f59e0b",
        grid: "#2563eb",
        export: "#10b981",
        load: "#ef4444"
      }
    }
  },
  plugins: []
};
