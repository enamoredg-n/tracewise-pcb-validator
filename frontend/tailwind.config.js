/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ember: {
          50: "#fff4eb",
          100: "#ffe4cf",
          200: "#ffc998",
          300: "#ffab61",
          400: "#ff8f3e",
          500: "#f97316",
          600: "#dd5f0e",
          700: "#b8490d",
          800: "#943b12",
          900: "#7a3313"
        },
        carbon: {
          950: "#090909",
          900: "#111111",
          850: "#171717",
          800: "#1d1d1d",
          700: "#292929"
        }
      },
      boxShadow: {
        aura: "0 24px 80px rgba(249, 115, 22, 0.18)",
        card: "0 18px 50px rgba(15, 15, 15, 0.12)"
      },
      backgroundImage: {
        "hero-grid":
          "radial-gradient(circle at 20% 20%, rgba(249,115,22,0.22), transparent 32%), radial-gradient(circle at 80% 0%, rgba(255,255,255,0.08), transparent 25%), linear-gradient(135deg, rgba(15,15,15,0.98) 0%, rgba(30,20,10,0.96) 40%, rgba(249,115,22,0.14) 100%)",
        "light-grid":
          "radial-gradient(circle at 15% 10%, rgba(249,115,22,0.16), transparent 28%), radial-gradient(circle at 85% 5%, rgba(15,15,15,0.08), transparent 24%), linear-gradient(135deg, rgba(255,250,245,1) 0%, rgba(255,245,236,1) 55%, rgba(255,234,214,0.92) 100%)"
      }
    },
  },
  plugins: [],
};
