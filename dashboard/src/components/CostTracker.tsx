"use client";

import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { TrendingUp, DollarSign, Clock } from "lucide-react";

interface CostTrackerProps {
    isActive: boolean;
    startTime: number | null;
}

export const CostTracker = ({ isActive, startTime }: CostTrackerProps) => {
    const [cost, setCost] = useState(0);
    const [duration, setDuration] = useState(0);
    const timerRef = useRef<NodeJS.Timeout | null>(null);

    // Gemini 2.5 Flash Native Audio Pricing (gemini-2.5-flash-native-audio-preview-12-2025)
    // Input (Audio): $3.00 / 1,000,000 audio tokens
    // Output (Audio): $12.00 / 1,000,000 audio tokens
    // Input (Text): $0.50 / 1,000,000 tokens
    // Output (Text): $2.00 / 1,000,000 tokens
    // Estimation: ~32 tokens/second for audio.
    // 1 min audio input ≈ 1920 tokens ($0.00576)
    // 1 min audio output ≈ 1920 tokens ($0.02304)
    // Average 50/50 conversation: ~$0.0144 / min.
    // Using a safe estimate for the demo: $0.03 per minute.
    const COST_PER_SECOND = 0.0005; // ($0.03 / 60)

    useEffect(() => {
        if (isActive && startTime) {
            timerRef.current = setInterval(() => {
                const now = Date.now();
                const diff = (now - startTime) / 1000;
                setDuration(diff);
                setCost(diff * COST_PER_SECOND);
            }, 100);
        } else {
            if (timerRef.current) clearInterval(timerRef.current);
        }

        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [isActive, startTime]);

    const formatDuration = (s: number) => {
        const mins = Math.floor(s / 60);
        const secs = Math.floor(s % 60);
        return `${mins}:${secs.toString().padStart(2, "0")}`;
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass-card flex items-center space-x-4 border-l-4 border-l-blue-500"
            >
                <div className="p-3 bg-blue-500/20 rounded-full">
                    <DollarSign className="w-6 h-6 text-blue-400" />
                </div>
                <div>
                    <p className="text-sm text-gray-400 font-medium">Estimated Cost</p>
                    <p className="text-2xl font-bold text-white tracking-tight">
                        ${cost.toFixed(4)}
                    </p>
                </div>
            </motion.div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="glass-card flex items-center space-x-4 border-l-4 border-l-purple-500"
            >
                <div className="p-3 bg-purple-500/20 rounded-full">
                    <Clock className="w-6 h-6 text-purple-400" />
                </div>
                <div>
                    <p className="text-sm text-gray-400 font-medium">Session Time</p>
                    <p className="text-2xl font-bold text-white tracking-tight">
                        {formatDuration(duration)}
                    </p>
                </div>
            </motion.div>
        </div>
    );
};
