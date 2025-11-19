import React from 'react';

/**
 * Simple avatar component for the ManyWorlds project.
 *
 * Accepts a `src` pointing to an image, an optional `alt` tag, and an
 * optional `size` (defaults to 120px).  This component uses a standard
 * `<img>` element rather than Next.js’s `<Image>` so that it can be used
 * both on the web and within other environments (e.g. Storybook).  In
 * production you may wish to create platform‑specific wrappers for
 * Next.js and React Native to handle their respective image components.
 */
export function Avatar({
  src,
  alt = 'Avatar',
  size = 120,
}: {
  src: string;
  alt?: string;
  size?: number;
}) {
  return (
    <img
      src={src}
      alt={alt}
      width={size}
      height={size}
      style={{ borderRadius: '50%' }}
    />
  );
}