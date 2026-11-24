import "./globals.css";

export const metadata = {
  title: "ClearanceHub — Faculty clearance",
  description: "A secure faculty clearance portal for students, clearance officers, and administrators."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
