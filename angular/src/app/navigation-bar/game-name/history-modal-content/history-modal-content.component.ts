import { Component, inject, OnInit } from '@angular/core';
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap';
import { TranslocoDirective } from '@ngneat/transloco';
import { TranslocoDatePipe, TranslocoDecimalPipe, TranslocoPercentPipe } from '@ngneat/transloco-locale';
import { AsyncPipe, KeyValue, KeyValuePipe, NgClass, NgFor, NgIf } from '@angular/common';
import { CurrentGameService } from '../../../ongoing-game/current-game.service';
import { Deck, decksDict, displayCardValue } from '../../../model/deck';
import { computeRoundStats, RoundStats } from '../../../model/round-stats';

interface HistoryEntryView {
  recordedAt: string;
  deck: Deck;
  stats: RoundStats;
}

@Component({
  selector: 'shpp-history-modal-content',
  standalone: true,
  templateUrl: './history-modal-content.component.html',
  styleUrls: ['./history-modal-content.component.scss'],
  imports: [TranslocoDirective, NgFor, NgIf, NgClass, AsyncPipe, KeyValuePipe, TranslocoDecimalPipe, TranslocoPercentPipe, TranslocoDatePipe]
})
export class HistoryModalContentComponent implements OnInit {
  activeModal = inject(NgbActiveModal);
  private currentGameService = inject(CurrentGameService);

  loading = true;
  entries: HistoryEntryView[] = [];

  displayCardValue = displayCardValue;
  Number = Number;
  round = Math.round;
  valueDescOrder = (a: KeyValue<string, number>, b: KeyValue<string, number>): number =>
    a.value > b.value ? -1 : (b.value > a.value ? 1 : 0)

  ngOnInit(): void {
    this.currentGameService.getHistory().then((entries) => {
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
}
