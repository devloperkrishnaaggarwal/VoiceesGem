"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic, MicOff, Phone, PhoneOff, Activity, ShieldCheck, Zap } from "lucide-react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { CostTracker } from "@/components/CostTracker";
import { cn } from "@/lib/utils";

export default function Home() {
    const [status, setStatus] = useState<"idle" | "connecting" | "active" | "error">("idle");
    const [startTime, setStartTime] = useState<number | null>(null);
    const [isMuted, setIsMuted] = useState(false);
    const clientRef = useRef<PipecatClient | null>(null);

    const audioRef = useRef<HTMLAudioElement>(null);

    const startCall = useCallback(async () => {
        setStatus("connecting");
        console.log("[DEBUG] Starting call...");

        try {
            if (clientRef.current) {
                console.log("[DEBUG] Disconnecting existing client");
                await clientRef.current.disconnect();
            }

            // SmallWebRTCTransport connects directly to the local bot via P2P WebRTC
            const transport = new SmallWebRTCTransport();
            const client = new PipecatClient({
                transport,
                enableMic: true
            });

            let connectionHandled = false;

            // CRITICAL: Monitor transportStateChanged for reliable connection detection
            // This event fires more reliably than the 'connected' event in some scenarios
            client.on("transportStateChanged", (state) => {
                console.log(`[DEBUG] 🔄 Transport state changed: ${state}`);

                // When state is 'connected' or 'ready', activate the UI
                if ((state === "connected" || state === "ready") && !connectionHandled) {
                    console.log("[DEBUG] ✅ Connection established via transportStateChanged!");
                    connectionHandled = true;
                    setStatus("active");
                    setStartTime(Date.now());
                }
            });

            client.on("connected", () => {
                console.log("[DEBUG] ✅ Client 'connected' event fired!");
                if (!connectionHandled) {
                    connectionHandled = true;
                    setStatus("active");
                    setStartTime(Date.now());
                }
            });

            client.on("disconnected", () => {
                console.log("[DEBUG] Client 'disconnected' event fired");
                connectionHandled = false;
                setStatus("idle");
                setStartTime(null);
            });

            client.on("error", (err: any) => {
                console.error("[DEBUG] ❌ Call error:", err);
                setStatus("error");
            });

            // Handle incoming audio tracks
            client.on("trackStarted", (track: MediaStreamTrack, participant: any) => {
                console.log(`[DEBUG] 🎧 Track started: ${track.kind}, id: ${track.id}`);
                if (track.kind === "audio") {
                    if (audioRef.current) {
                        console.log("[DEBUG] 🔊 Attaching audio track to element");
                        audioRef.current.srcObject = new MediaStream([track]);
                        audioRef.current.play().catch(e => console.error("[DEBUG] Audio play failed:", e));
                    } else {
                        console.warn("[DEBUG] ⚠️ Audio element ref is null");
                    }
                }
            });

            client.on("trackStopped", (track: MediaStreamTrack) => {
                console.log(`[DEBUG] 🛑 Track stopped: ${track.kind}`);
                // Optional: cleanup if needed, but browser handles stream ending
            });

            // Log all events for debugging
            (transport as any).on?.("*", (event: string, ...args: any[]) => {
                console.log(`[DEBUG] Transport event: ${event}`, args);
            });

            // SmallWebRTC connects via P2P signaling - needs the bot's endpoint URL
            const rawBotUrl = process.env.NEXT_PUBLIC_BOT_URL || "http://localhost:7860";
            const botUrl = rawBotUrl.replace(/\/+$/, ''); // Remove trailing slashes
            console.log("[DEBUG] Connecting to local bot via SmallWebRTC at:", botUrl);

            // Pass the endpoint for WebRTC offer/answer exchange
            await client.connect({
                webrtcRequestParams: {
                    endpoint: `${botUrl}/api/offer`,
                }
            });

            console.log("[DEBUG] connect() completed - WebRTC connection established");

            // Fallback polling to ensure UI updates even if events are missed
            let pollAttempts = 0;
            const maxPollAttempts = 10; // 3 seconds total

            const connectionPoll = setInterval(() => {
                pollAttempts++;
                const isConnected = client.connected;
                const currentState = client.state;

                console.log(`[DEBUG] 🔍 Poll ${pollAttempts}/${maxPollAttempts}: connected=${isConnected}, state=${currentState}`);

                if (isConnected && !connectionHandled) {
                    console.log("[DEBUG] ✅ Connection detected via polling!");
                    clearInterval(connectionPoll);
                    connectionHandled = true;
                    setStatus("active");
                    setStartTime(Date.now());
                } else if (pollAttempts >= maxPollAttempts) {
                    console.warn("[DEBUG] ⚠️ Connection polling timeout");
                    clearInterval(connectionPoll);

                    if (client.connected) {
                        console.log("[DEBUG] ✅ Connection IS established! Activating UI");
                        connectionHandled = true;
                        setStatus("active");
                        setStartTime(Date.now());
                    }
                }
            }, 300);

            clientRef.current = client;
            console.log("[DEBUG] Client stored in ref");
        } catch (err) {
            console.error("[DEBUG] ❌ Failed to start call:", err);
            setStatus("error");
        }
    }, []);

    const endCall = useCallback(async () => {
        if (clientRef.current) {
            await clientRef.current.disconnect();
            clientRef.current = null;
        }
        setStatus("idle");
        setStartTime(null);
    }, []);

    const toggleMute = useCallback(() => {
        if (clientRef.current) {
            const newMute = !isMuted;
            clientRef.current.enableMic(!newMute);
            setIsMuted(newMute);
        }
    }, [isMuted]);

    return (
        <main className="relative flex min-h-screen flex-col items-center justify-center p-6 md:p-24 overflow-hidden bg-black">
            <audio ref={audioRef} autoPlay style={{ display: "none" }} />
            {/* Background Orbs */}
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/20 rounded-full blur-[120px] animate-pulse-slow" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/20 rounded-full blur-[120px] animate-pulse-slow" />

            {/* Header */}
            <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
                className="z-10 text-center mb-12"
            >
                <h1 className="text-5xl md:text-7xl font-black bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500 mb-4 tracking-tighter italic">
                    VOICEE <span className="text-white not-italic">LIVE</span>
                </h1>
                <p className="text-gray-400 text-lg md:text-xl font-medium max-w-lg mx-auto leading-relaxed">
                    Premium AI Voice Assistant with Real-Time <span className="text-blue-400 font-bold">Cost</span>.
                </p>
            </motion.div>

            {/* Main Console */}
            <div className="z-10 flex flex-col items-center w-full max-w-4xl space-y-8">

                {/* Status Badge */}
                <motion.div
                    animate={status === "active" ? { scale: [1, 1.05, 1] } : {}}
                    transition={{ repeat: Infinity, duration: 2 }}
                    className={cn(
                        "px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-widest glass border flex items-center space-x-2",
                        status === "active" ? "bg-green-500/10 border-green-500/30 text-green-400" :
                            status === "connecting" ? "bg-yellow-500/10 border-yellow-500/30 text-yellow-400" :
                                status === "error" ? "bg-red-500/10 border-red-500/30 text-red-400" :
                                    "bg-blue-500/10 border-blue-500/30 text-blue-400"
                    )}
                >
                    <div className={cn("w-2 h-2 rounded-full",
                        status === "active" ? "bg-green-400 animate-ping" :
                            status === "connecting" ? "bg-yellow-400 animate-pulse" :
                                status === "error" ? "bg-red-400" : "bg-blue-400"
                    )} />
                    <span>{status === "active" ? "Live Connection" : status.replace(/^\w/, (c) => c.toUpperCase())}</span>
                </motion.div>

                {/* Visualizer Area */}
                <div className="relative w-64 h-64 md:w-80 md:h-80 flex items-center justify-center">
                    <div className="absolute inset-0 bg-blue-500/5 rounded-full border border-blue-500/10 blur-xl" />

                    <AnimatePresence mode="wait">
                        {status === "active" ? (
                            <motion.div
                                key="active"
                                initial={{ scale: 0.8, opacity: 0 }}
                                animate={{ scale: 1, opacity: 1 }}
                                exit={{ scale: 0.8, opacity: 0 }}
                                className="relative flex items-center justify-center"
                            >
                                <div className="absolute w-40 h-40 bg-blue-500/20 rounded-full animate-ping" />
                                <div className="absolute w-32 h-32 bg-blue-500/30 rounded-full animate-pulse" />
                                <Activity className="w-16 h-16 text-blue-400 z-20" />
                            </motion.div>
                        ) : (
                            <motion.div
                                key="idle"
                                initial={{ scale: 0.8, opacity: 0 }}
                                animate={{ scale: 1, opacity: 1 }}
                                exit={{ scale: 0.8, opacity: 0 }}
                                className="flex flex-col items-center justify-center space-y-4"
                            >
                                <Mic className="w-16 h-16 text-gray-600 opacity-50" />
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>

                {/* Cost Tracker Component */}
                <CostTracker isActive={status === "active"} startTime={startTime} />

                {/* Controls */}
                <div className="flex items-center space-x-6 pt-4">
                    {status === "active" && (
                        <button
                            onClick={toggleMute}
                            className={cn(
                                "p-4 rounded-full glass border transition-all duration-300",
                                isMuted ? "bg-red-500/20 border-red-500/40 text-red-400" : "hover:bg-white/10 text-white"
                            )}
                        >
                            {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                        </button>
                    )}

                    <button
                        onClick={status === "active" ? endCall : startCall}
                        disabled={status === "connecting"}
                        className={cn(
                            "px-8 py-4 rounded-full font-bold text-lg flex items-center space-x-3 transition-all duration-500 shadow-2xl",
                            status === "active"
                                ? "bg-red-500 hover:bg-red-600 text-white shadow-red-500/20"
                                : "bg-blue-600 hover:bg-blue-700 text-white shadow-blue-600/20"
                        )}
                    >
                        {status === "active" ? (
                            <>
                                <PhoneOff className="w-6 h-6" />
                                <span>End Conversation</span>
                            </>
                        ) : (
                            <>
                                <Phone className="w-6 h-6" />
                                <span>Start AI Call</span>
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Footer Features */}
            <div className="z-10 grid grid-cols-1 md:grid-cols-3 gap-6 mt-20 w-full max-w-5xl">
                <FeatureCard
                    icon={<ShieldCheck className="w-5 h-5 text-blue-400" />}
                    title="Native Audio"
                    desc="Powered by Gemini 2.5 Flash for ultra-low latency speech-to-speech."
                />
                <FeatureCard
                    icon={<Zap className="w-5 h-5 text-yellow-400" />}
                    title="Real-time Tracking"
                    desc="Transparent billing updates as you speak, down to the millisecond."
                />
                <FeatureCard
                    icon={<Mic className="w-5 h-5 text-purple-400" />}
                    title="HD Quality"
                    desc="Crystal clear audio processing with advanced noise cancellation."
                />
            </div>
        </main>
    );
}

function FeatureCard({ icon, title, desc }: { icon: any, title: string, desc: string }) {
    return (
        <div className="glass-card flex flex-col items-start space-y-2 group hover:border-blue-500/40 transition-colors">
            <div className="p-2 bg-white/5 rounded-lg group-hover:bg-blue-500/10 transition-colors">
                {icon}
            </div>
            <h3 className="font-bold text-white tracking-tight">{title}</h3>
            <p className="text-sm text-gray-400 leading-relaxed font-medium">
                {desc}
            </p>
        </div>
    );
}
