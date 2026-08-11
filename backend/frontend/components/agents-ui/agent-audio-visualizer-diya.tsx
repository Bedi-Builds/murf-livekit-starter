'use client';

import React from 'react';
import { motion } from 'motion/react';
import { cn } from '@/lib/shadcn/utils';

type AgentState = 'disconnected' | 'connecting' | 'initializing' | 'listening' | 'thinking' | 'speaking';

interface AgentAudioVisualizerDiyaProps {
  state?: AgentState;
  color?: `#${string}`;
  className?: string;
}

// Motion presets per agent state — each controls how the flame moves and glows
const FLAME_MOTION: Record<AgentState, any> = {
  disconnected: {
    scaleY: [0.5, 0.5],
    scaleX: [0.5, 0.5],
    opacity: [0.35, 0.35],
    rotate: [0, 0],
  },
  connecting: {
    scaleY: [0.7, 0.85, 0.7],
    scaleX: [0.85, 0.95, 0.85],
    opacity: [0.5, 0.7, 0.5],
    rotate: [-1, 1, -1],
  },
  initializing: {
    scaleY: [0.7, 0.85, 0.7],
    scaleX: [0.85, 0.95, 0.85],
    opacity: [0.5, 0.7, 0.5],
    rotate: [-1, 1, -1],
  },
  listening: {
    scaleY: [0.9, 1, 0.9],
    scaleX: [0.95, 1.02, 0.95],
    opacity: [0.75, 0.9, 0.75],
    rotate: [-2, 2, -2],
  },
  thinking: {
    scaleY: [0.85, 1.05, 0.85],
    scaleX: [0.9, 1, 0.9],
    opacity: [0.7, 1, 0.7],
    rotate: [-3, 3, -3],
  },
  speaking: {
    scaleY: [1, 1.25, 1.05, 1.2, 1],
    scaleX: [1, 1.1, 0.95, 1.08, 1],
    opacity: [0.9, 1, 0.95, 1, 0.9],
    rotate: [-4, 4, -3, 3, -4],
  },
};

const FLAME_DURATION: Record<AgentState, number> = {
  disconnected: 2,
  connecting: 1.6,
  initializing: 1.6,
  listening: 1.4,
  thinking: 0.9,
  speaking: 0.6,
};

export function AgentAudioVisualizerDiya({
  state = 'disconnected',
  color = '#E8A33D',
  className,
}: AgentAudioVisualizerDiyaProps) {
  const motionProps = FLAME_MOTION[state] ?? FLAME_MOTION.disconnected;
  const duration = FLAME_DURATION[state] ?? 2;
  const haloOpacity = state === 'speaking' ? 0.55 : state === 'listening' ? 0.35 : state === 'thinking' ? 0.4 : 0.15;
  const haloScale = state === 'speaking' ? 1.6 : state === 'listening' ? 1.35 : 1.15;

  return (
    <div className={cn('relative flex items-center justify-center', className)}>
      {/* Glow halo behind the flame */}
      <motion.div
        className="absolute rounded-full blur-2xl"
        style={{
          width: '55%',
          height: '55%',
          backgroundColor: color,
        }}
        animate={{
          opacity: haloOpacity,
          scale: haloScale,
        }}
        transition={{
          duration: duration * 1.5,
          repeat: Infinity,
          repeatType: 'reverse',
          ease: 'easeInOut',
        }}
      />

      <svg viewBox="0 0 200 260" className="relative h-full w-full" fill="none">
        <defs>
          <linearGradient id="flameGradient" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor={color} stopOpacity="0.9" />
            <stop offset="55%" stopColor={color} stopOpacity="1" />
            <stop offset="100%" stopColor="#FFF3D6" stopOpacity="1" />
          </linearGradient>
          <linearGradient id="lampGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#B9863C" />
            <stop offset="100%" stopColor="#8A621F" />
          </linearGradient>
        </defs>

        {/* Flame */}
        <motion.path
          d="M100 60 C130 100, 135 140, 100 175 C65 140, 70 100, 100 60 Z"
          fill="url(#flameGradient)"
          style={{ originX: '0.5', originY: '1' }}
          animate={motionProps}
          transition={{
            duration,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />

        {/* Diya (lamp) base */}
        <path
          d="M30 190 C30 175, 70 168, 100 168 C130 168, 170 175, 170 190 C170 205, 130 212, 100 212 C70 212, 30 205, 30 190 Z"
          fill="url(#lampGradient)"
        />
        {/* Diya rim highlight */}
        <ellipse cx="100" cy="188" rx="62" ry="10" fill="#D9A855" opacity="0.5" />
      </svg>
    </div>
  );
}