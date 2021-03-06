import os
import time
import unittest
from unittest.mock import MagicMock, patch

import termtosvg.anim as anim
from termtosvg import term
from termtosvg.asciicast import AsciiCastV2Header, AsciiCastV2Event, AsciiCastV2Theme

commands = [
    'echo $SHELL && sleep 0.1;\r\n',
    'tree && 0.1;\r\n',
    'ls && sleep 0.1;\r\n',
    'w',
    'h',
    'o',
    'a',
    'm',
    'i\r\n',
    'exit;\r\n'
]


class TestTerm(unittest.TestCase):
    def test__record(self):
        # Use pipes in lieu of stdin and stdout
        fd_in_read, fd_in_write = os.pipe()
        fd_out_read, fd_out_write = os.pipe()

        lines = 24
        columns = 80

        pid = os.fork()
        if pid == 0:
            # Child process
            for line in commands:
                os.write(fd_in_write, line.encode('utf-8'))
                time.sleep(0.060)
            os._exit(0)

        # Parent process
        with term.TerminalMode(fd_in_read):
            for _ in term._record(columns, lines, fd_in_read, fd_out_write):
                pass

        os.waitpid(pid, 0)
        for fd in fd_in_read, fd_in_write, fd_out_read, fd_out_write:
            os.close(fd)

    def test_record(self):
        # Use pipes in lieu of stdin and stdout
        fd_in_read, fd_in_write = os.pipe()
        fd_out_read, fd_out_write = os.pipe()

        lines = 24
        columns = 80

        pid = os.fork()
        if pid == 0:
            # Child process
            for line in commands:
                os.write(fd_in_write, line.encode('utf-8'))
                time.sleep(0.060)
            os._exit(0)

        # Parent process
        with term.TerminalMode(fd_in_read):
            for _ in term.record(columns, lines, fd_in_read, fd_out_write):
                pass

        os.waitpid(pid, 0)
        for fd in fd_in_read, fd_in_write, fd_out_read, fd_out_write:
            os.close(fd)

    def test_replay(self):
        def pyte_to_str(x, _):
            return x.data

        fallback_theme = AsciiCastV2Theme('#000000', '#000000', ':'.join(['#000000'] * 16))
        theme = AsciiCastV2Theme('#000000', '#FFFFFF', ':'.join(['#123456'] * 16))

        with self.subTest(case='One shell command per event'):
            nbr_records = 5

            records = [AsciiCastV2Header(version=2, width=80, height=24, theme=theme)] + \
                      [AsciiCastV2Event(time=i,
                                        event_type='o',
                                        event_data='{}\r\n'.format(i).encode('utf-8'),
                                        duration=None)
                       for i in range(1, nbr_records)]

            records = term.replay(records, pyte_to_str, None, fallback_theme, 50, 1000)
            # Last blank line is the cursor
            lines = [str(i) for i in range(nbr_records)] + [' ']
            for i, record in enumerate(records):
                # Skip header and cursor line
                if i == 0:
                    pass
                else:
                    self.assertEqual(record.line[0], lines[i])

        with self.subTest(case='Shell command spread over multiple lines, no theme'):
            records = [AsciiCastV2Header(version=2, width=80, height=24, theme=None)] + \
                      [AsciiCastV2Event(time=i * 60,
                                        event_type='o',
                                        event_data=data.encode('utf-8'),
                                        duration=None)
                       for i, data in enumerate(commands)]

            screen = {}
            for record in term.replay(records, pyte_to_str, None, theme, 50, 1000):
                if hasattr(record, 'line'):
                    screen[record.row] = ''.join(record.line[i] for i in sorted(record.line))

            cmds = [cmd for cmd in ''.join(commands).split('\r\n') if cmd]
            cursor = [' ']
            expected_screen = dict(enumerate(cmds + cursor))
            self.assertEqual(expected_screen, screen)

        with self.subTest(case='Hidden cursor'):
            # '\u001b[?25h' : display cursor
            # '\u001b[?25l' : hide cursor
            records = [AsciiCastV2Header(version=2, width=80, height=24, theme=None)] + \
                      [
                          AsciiCastV2Event(0, 'o', '\u001b[?25haaaa'.encode('utf-8'), None),
                          AsciiCastV2Event(100, 'o', '\r\n\u001b[?25lbbbb'.encode('utf-8'), None),
                          AsciiCastV2Event(200, 'o', '\r\n\u001b[?25hcccc'.encode('utf-8'), None),
                      ]

            gen = term.replay(records, anim.CharacterCell.from_pyte, None, theme, 50, 1000)
            header, *events = list(gen)

            # Event #0: First line - cursor displayed after 'aaaa'
            self.assertEqual(events[0].row, 0)
            self.assertEqual(events[0].line[4].color, theme.bg)
            self.assertEqual(events[0].line[4].background_color, theme.fg)

            # Event #1: First line - cursor removed at position 4
            self.assertEqual(events[1].row, 0)
            self.assertNotIn(4, events[1].line)

            # Event #2: Second line - cursor hidden
            self.assertEqual(events[2].row, 1)
            self.assertNotIn(4, events[2].line)

            # Event #3: Third line - cursor displayed after 'cccc'
            self.assertEqual(events[3].row, 2)
            self.assertEqual(events[3].line[4].color, theme.bg)
            self.assertEqual(events[3].line[4].background_color, theme.fg)

    def test_get_terminal_size(self):
        with self.subTest(case='Successful get_terminal_size call'):
            term_size_mock = MagicMock(return_value=(42, 84))
            with patch('os.get_terminal_size', term_size_mock):
                cols, lines, = term.get_terminal_size(-1)
                self.assertEqual(cols, 42)
                self.assertEqual(lines, 84)

    def test__group_by_time(self):
        event_records = [
            AsciiCastV2Event(0, 'o', b'1', None),
            AsciiCastV2Event(50, 'o', b'2', None),
            AsciiCastV2Event(80, 'o', b'3', None),
            AsciiCastV2Event(200, 'o', b'4', None),
            AsciiCastV2Event(210, 'o', b'5', None),
            AsciiCastV2Event(300, 'o', b'6', None),
            AsciiCastV2Event(310, 'o', b'7', None),
            AsciiCastV2Event(320, 'o', b'8', None),
            AsciiCastV2Event(330, 'o', b'9', None)
        ]

        grouped_event_records = [
            AsciiCastV2Event(0, 'o', b'1', 50),
            AsciiCastV2Event(50, 'o', b'23', 150),
            AsciiCastV2Event(200, 'o', b'45', 100),
            AsciiCastV2Event(300, 'o', b'6789', 1234)
        ]

        result = list(term._group_by_time(event_records, 50, 1234))
        self.assertEqual(grouped_event_records, result)
