import Image from 'next/image';
import Link from 'next/link';

/**
 * Home page of the web application.
 *
 * Displays a 2D scientist avatar at the top of the page followed by
 * navigation links to the Views, Papers, and Interviews sections.  This
 * placeholder UI can be replaced with dynamic data once you implement
 * API endpoints in your FastAPI services and route handlers in Next.js.
 */
export default function Home() {
  return (
    <main style={{ padding: '2rem', maxWidth: '800px', margin: '0 auto' }}>
      <header style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <Image
          src="/avatar.png"
          alt="Scientist avatar"
          width={120}
          height={120}
        />
        <h1>ManyWorlds</h1>
        <p>Explore views, papers, and interviews of leading scientists.</p>
      </header>
      <nav
        style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '1rem',
          marginBottom: '2rem',
        }}
      >
        <Link
          href="/views"
          style={{
            padding: '0.5rem 1rem',
            border: '1px solid #ccc',
            borderRadius: '4px',
            textDecoration: 'none',
            color: '#333',
          }}
        >
          Views
        </Link>
        <Link
          href="/papers"
          style={{
            padding: '0.5rem 1rem',
            border: '1px solid #ccc',
            borderRadius: '4px',
            textDecoration: 'none',
            color: '#333',
          }}
        >
          Papers
        </Link>
        <Link
          href="/interviews"
          style={{
            padding: '0.5rem 1rem',
            border: '1px solid #ccc',
            borderRadius: '4px',
            textDecoration: 'none',
            color: '#333',
          }}
        >
          Interviews
        </Link>
      </nav>
      <section>
        <p>
          This is a placeholder for content. Select a menu item to explore.
        </p>
      </section>
    </main>
  );
}