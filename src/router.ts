import {
  Channel,
  NewMessage,
  OutboundMessage,
  OutboundMessagePart,
} from './types.js';
import { formatLocalTime } from './timezone.js';

export function escapeXml(s: string): string {
  if (!s) return '';
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function formatMessages(
  messages: NewMessage[],
  timezone: string,
): string {
  const lines = messages.map((m) => {
    const displayTime = formatLocalTime(m.timestamp, timezone);
    return `<message sender="${escapeXml(m.sender_name)}" time="${escapeXml(displayTime)}">${escapeXml(m.content)}</message>`;
  });

  const header = `<context timezone="${escapeXml(timezone)}" />\n`;

  return `${header}<messages>\n${lines.join('\n')}\n</messages>`;
}

export function stripInternalTags(text: string): string {
  return text.replace(/<internal>[\s\S]*?<\/internal>/g, '').trim();
}

export function formatOutbound(rawText: string): string {
  const text = stripInternalTags(rawText);
  if (!text) return '';
  return text;
}

export function formatOutboundMessage(message: OutboundMessage): OutboundMessage {
  const parts: OutboundMessagePart[] = [];

  for (const part of message.parts) {
    if (part.type === 'text') {
      const text = formatOutbound(part.text);
      if (text) parts.push({ type: 'text', text });
      continue;
    }
    const caption = part.caption ? formatOutbound(part.caption) || undefined : undefined;
    parts.push({ ...part, caption });
  }

  return { parts };
}

export function routeOutbound(
  channels: Channel[],
  jid: string,
  text: string,
): Promise<void> {
  const channel = channels.find((c) => c.ownsJid(jid) && c.isConnected());
  if (!channel) throw new Error(`No channel for JID: ${jid}`);
  return channel.sendMessage(jid, text);
}

export async function routeOutboundMessage(
  channels: Channel[],
  jid: string,
  message: OutboundMessage,
): Promise<void> {
  const channel = channels.find((c) => c.ownsJid(jid) && c.isConnected());
  if (!channel) throw new Error(`No channel for JID: ${jid}`);

  const formatted = formatOutboundMessage(message);
  if (formatted.parts.length === 0) return;

  const hasNonText = formatted.parts.some((part) => part.type !== 'text');
  if (!hasNonText) {
    for (const part of formatted.parts) {
      if (part.type !== 'text') continue;
      await channel.sendMessage(jid, part.text);
    }
    return;
  }

  if (!channel.sendMediaMessage) {
    throw new Error(`Channel ${channel.name} does not support media messages`);
  }

  await channel.sendMediaMessage(jid, formatted);
}

export function findChannel(
  channels: Channel[],
  jid: string,
): Channel | undefined {
  return channels.find((c) => c.ownsJid(jid));
}
