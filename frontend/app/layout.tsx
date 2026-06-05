import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'DataVerse AI',
  description: 'Proactive AI Data Platform',
  icons: {
    icon: '/icon.svg',
    shortcut: '/icon.svg',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased bg-[#0b1326] text-white selection:bg-violet-500/30 overflow-hidden" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
