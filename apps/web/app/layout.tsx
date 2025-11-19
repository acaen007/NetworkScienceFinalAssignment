import type { ReactNode } from 'react';
import './globals.css';

export const metadata = {
  title: 'ManyWorlds Prototype',
  description: 'A prototype for the ManyWorlds project',
};

/**
 * Root layout for the web application.
 *
 * Next.js 14 uses the App Router by default under `app/`.  This layout
 * composes every page and includes the global stylesheet.  You can add
 * providers (e.g. React Query, Redux) here in the future.
 */
export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}