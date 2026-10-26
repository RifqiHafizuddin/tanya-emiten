import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tanya Emiten",
  description: "Cited answers about LQ45 companies from their annual reports. Not investment advice.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
