export const metadata = {
  title: "Campus Talent Connect",
  description: "Student-focused freelancing platform",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
