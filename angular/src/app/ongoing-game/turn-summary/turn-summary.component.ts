import { AfterViewInit, Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';
import { PlayerState } from '../../model/events';
import { filter, map, Observable, Subscription, tap, withLatestFrom } from 'rxjs';
import { Deck, decksDict, displayCardValue } from '../../model/deck';
import { CardCount, computeRoundStats } from '../../model/round-stats';
import { AsyncPipe, KeyValue, KeyValuePipe, NgClass, NgFor } from '@angular/common';
import { CurrentGameService } from '../current-game.service';
import confetti from 'canvas-confetti';
import { TranslocoDecimalPipe, TranslocoPercentPipe } from '@ngneat/transloco-locale';
import { TranslocoDirective } from '@ngneat/transloco';

@Component({
    selector: 'shpp-turn-summary',
    templateUrl: './turn-summary.component.html',
    styleUrls: ['./turn-summary.component.scss'],
    standalone: true,
    imports: [TranslocoDirective, NgFor, NgClass, AsyncPipe, KeyValuePipe, TranslocoDecimalPipe, TranslocoPercentPipe]
})
export class TurnSummaryComponent implements AfterViewInit, OnDestroy {
  private subscriptions: Subscription[] = [];

  displayCardValue = displayCardValue;
  Number = Number;
  round = Math.round;
  valueDescOrder = (a: KeyValue<string, number>, b: KeyValue<string, number>): number =>
    a.value > b.value ? -1 : (b.value > a.value ? 1 : 0)

  deck: Deck = decksDict['FIBONACCI'];
  average = 0;
  agreement = 0;
  $counts: Observable<CardCount>;
  private $playerStates: Observable<PlayerState[]>;
  private $agreement: Observable<number>;

  @ViewChild('agreementElement')
  private agreementElement?: ElementRef;

  constructor(private currentGameService: CurrentGameService) {
    this.$playerStates = this.currentGameService.state$
    .pipe(
      withLatestFrom(this.currentGameService.gameInfo$),
      filter(([, gameInfo]) => gameInfo !== null && gameInfo.revealed),
      tap(([, gameInfo]) => {
        if (gameInfo) {
          this.deck = decksDict[gameInfo.deck];
        }
      }),
      map(([gameState]) => Object.values(gameState)),
      map((playerStates: PlayerState[]) => playerStates.filter((state) => state.hand !== undefined && state.hand !== null))
    );

    const $roundStats = this.$playerStates
    .pipe(map((players: PlayerState[]) => computeRoundStats(players.map((player) => player.hand || 0))));

    this.$counts = $roundStats.pipe(map((stats) => stats.counts));
    this.$agreement = $roundStats.pipe(map((stats) => stats.agreement));

    this.subscriptions.concat(
      $roundStats
      .subscribe((stats) => this.average = stats.average));

    this.subscriptions.concat(
      this.$agreement
      .subscribe((value) => this.agreement = value));
  }

  ngAfterViewInit(): void {
    this.subscriptions.concat(
      this.$agreement
      .pipe(filter((value) => value === 1))
      .subscribe(() => this.fireConfettis()));
  }

  agreementClass(): string {
    if (this.agreement === 0) {
      return '';
    } else if (this.agreement < .5) {
      return 'text-danger';
    } else if (this.agreement < .7) {
      return 'text-warning';
    } else {
      return 'text-success';
    }
  }

  ngOnDestroy(): void {
    this.subscriptions.forEach((s) => s.unsubscribe());
  }

  private fireConfettis() {
    const domRect = this.agreementElement?.nativeElement.getBoundingClientRect();
    const x = (domRect.left + domRect.width / 2) / window.innerWidth;
    const y = (domRect.top + domRect.height / 2) / window.innerHeight;
    const origin = { x: x, y: y };
    this.fireParticles(0.25, {
      origin: origin,
      spread: 26,
      startVelocity: 55,
    });
    this.fireParticles(0.2, {
      origin: origin,
      spread: 60,
    });
    this.fireParticles(0.35, {
      origin: origin,
      spread: 100,
      decay: 0.91,
      scalar: 0.8
    });
    this.fireParticles(0.1, {
      origin: origin,
      spread: 120,
      startVelocity: 25,
      decay: 0.92,
      scalar: 1.2
    });
    this.fireParticles(0.1, {
      origin: origin,
      spread: 120,
      startVelocity: 45,
    });
  }

  private fireParticles(particleRatio: number, opts: any) {
    confetti({
      ...opts,
      disableForReducedMotion: true,
      particleCount: Math.floor(200 * particleRatio)
    });
  }
}
