import { Component, inject, OnInit } from '@angular/core';
import { NgbActiveModal, NgbTooltip } from '@ng-bootstrap/ng-bootstrap';
import { TranslocoDirective } from '@ngneat/transloco';
import { TranslocoDatePipe, TranslocoDecimalPipe, TranslocoPercentPipe } from '@ngneat/transloco-locale';
import { AsyncPipe, KeyValue, KeyValuePipe, NgClass, NgFor, NgIf } from '@angular/common';
import { CurrentGameService } from '../../../ongoing-game/current-game.service';
import { HistoryEntry } from '../../../model/events';
import { Deck, decksDict, displayCardValue } from '../../../model/deck';
import { computeRoundStats, RoundStats } from '../../../model/round-stats';

interface HistoryEntryView {
  recordedAt: string;
  deck: Deck;
  stats: RoundStats;
}

const CSV_COLUMNS = ['recordedAt', 'deck', 'playerName', 'spectator', 'hand'];

@Component({
  selector: 'shpp-history-modal-content',
  standalone: true,
  templateUrl: './history-modal-content.component.html',
  styleUrls: ['./history-modal-content.component.scss'],
  imports: [TranslocoDirective, NgFor, NgIf, NgClass, AsyncPipe, KeyValuePipe, TranslocoDecimalPipe, TranslocoPercentPipe, TranslocoDatePipe, NgbTooltip]
})
export class HistoryModalContentComponent implements OnInit {
  activeModal = inject(NgbActiveModal);
  private currentGameService = inject(CurrentGameService);

  loading = true;
  entries: HistoryEntryView[] = [];
  private rawEntries: HistoryEntry[] = [];

  displayCardValue = displayCardValue;
  Number = Number;
  round = Math.round;
  valueDescOrder = (a: KeyValue<string, number>, b: KeyValue<string, number>): number =>
    a.value > b.value ? -1 : (b.value > a.value ? 1 : 0)

  ngOnInit(): void {
    this.currentGameService.getHistory().then((entries) => {
      this.rawEntries = entries;
      this.entries = entries.map((entry) => ({
        recordedAt: entry.recordedAt,
        deck: decksDict[entry.deck],
        stats: computeRoundStats(
          entry.players
          .filter((player) => player.hand !== undefined && player.hand !== null)
          .map((player) => player.hand as number)
        )
      }));
      this.loading = false;
    });
  }

  agreementClass(agreement: number): string {
    if (agreement === 0) {
      return '';
    } else if (agreement < .5) {
      return 'text-danger';
    } else if (agreement < .7) {
      return 'text-warning';
    } else {
      return 'text-success';
    }
  }

  exportJson(): void {
    this.download(JSON.stringify(this.rawEntries, null, 2), 'history.json', 'application/json');
  }

  exportCsv(): void {
    const rows = this.rawEntries.flatMap((entry) => entry.players.map((player) => [
      entry.recordedAt, entry.deck, player.name, String(player.spectator), player.hand ?? ''
    ]));
    const csv = [CSV_COLUMNS, ...rows]
    .map((row) => row.map(HistoryModalContentComponent.escapeCsvField).join(','))
    .join('\r\n');
    this.download(csv, 'history.csv', 'text/csv');
  }

  private static escapeCsvField(field: unknown): string {
    const text = String(field);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  private download(content: string, filename: string, mimeType: string): void {
    const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }
}
