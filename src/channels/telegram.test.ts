import fs from 'fs';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./registry.js', () => ({ registerChannel: vi.fn() }));
vi.mock('../env.js', () => ({ readEnvFile: vi.fn(() => ({})) }));
vi.mock('../config.js', () => ({
  ASSISTANT_NAME: 'Andy',
  TRIGGER_PATTERN: /^@Andy\b/i,
}));
vi.mock('../logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

type Handler = (...args: any[]) => any;
const botRef = vi.hoisted(() => ({ current: null as any }));

vi.mock('grammy', () => ({
  InputFile: class MockInputFile {
    path: unknown;
    filename?: string;

    constructor(path: unknown, filename?: string) {
      this.path = path;
      this.filename = filename;
    }
  },
  Bot: class MockBot {
    token: string;
    commandHandlers = new Map<string, Handler>();
    filterHandlers = new Map<string, Handler[]>();
    errorHandler: Handler | null = null;
    api = {
      sendMessage: vi.fn().mockResolvedValue(undefined),
      sendChatAction: vi.fn().mockResolvedValue(undefined),
      sendPhoto: vi.fn().mockResolvedValue(undefined),
    };

    constructor(token: string) {
      this.token = token;
      botRef.current = this;
    }

    command(name: string, handler: Handler) {
      this.commandHandlers.set(name, handler);
    }

    on(filter: string, handler: Handler) {
      const existing = this.filterHandlers.get(filter) || [];
      existing.push(handler);
      this.filterHandlers.set(filter, existing);
    }

    catch(handler: Handler) {
      this.errorHandler = handler;
    }

    start(opts: { onStart: (botInfo: any) => void }) {
      opts.onStart({ username: 'pathclaw_bot', id: 12345 });
    }

    stop() {}
  },
}));

import { TelegramChannel, TelegramChannelOpts } from './telegram.js';

function currentBot() {
  return botRef.current;
}

function createTestOpts(
  overrides?: Partial<TelegramChannelOpts>,
): TelegramChannelOpts {
  return {
    onMessage: vi.fn(),
    onChatMetadata: vi.fn(),
    registeredGroups: vi.fn(() => ({
      'tg:100200300': {
        name: 'Test Group',
        folder: 'telegram_test-group',
        trigger: '@Andy',
        added_at: '2024-01-01T00:00:00.000Z',
      },
    })),
    ...overrides,
  };
}

describe('TelegramChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('connects and registers handlers', async () => {
    const channel = new TelegramChannel('token', createTestOpts());
    await channel.connect();

    expect(channel.isConnected()).toBe(true);
    expect(currentBot().commandHandlers.has('chatid')).toBe(true);
    expect(currentBot().filterHandlers.has('message:text')).toBe(true);
  });

  it('sends text messages', async () => {
    const channel = new TelegramChannel('token', createTestOpts());
    await channel.connect();

    await channel.sendMessage('tg:100200300', 'hello');

    expect(currentBot().api.sendMessage).toHaveBeenCalledWith('100200300', 'hello');
  });

  it('sends media parts sequentially', async () => {
    const channel = new TelegramChannel('token', createTestOpts());
    await channel.connect();

    const existsSpy = vi.spyOn(fs, 'existsSync').mockReturnValue(true);
    const streamSpy = vi
      .spyOn(fs, 'createReadStream')
      .mockReturnValue({ path: '/tmp/thumb.png' } as any);

    await channel.sendMediaMessage('tg:100200300', {
      parts: [
        { type: 'text', text: 'summary first' },
        { type: 'image', path: '/tmp/thumb.png', caption: 'thumb' },
        { type: 'text', text: 'summary after' },
      ],
    });

    expect(currentBot().api.sendMessage).toHaveBeenNthCalledWith(
      1,
      '100200300',
      'summary first',
    );
    expect(currentBot().api.sendPhoto).toHaveBeenCalledWith(
      '100200300',
      expect.objectContaining({
        filename: 'thumb.png',
        path: expect.objectContaining({ path: '/tmp/thumb.png' }),
      }),
      { caption: 'thumb' },
    );
    expect(currentBot().api.sendMessage).toHaveBeenNthCalledWith(
      2,
      '100200300',
      'summary after',
    );

    existsSpy.mockRestore();
    streamSpy.mockRestore();
  });
});
