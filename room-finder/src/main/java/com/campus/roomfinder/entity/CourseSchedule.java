package com.campus.roomfinder.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.Setter;
import org.springframework.data.annotation.Id;

import java.time.LocalTime;

@Entity
@Table(name = "course_schedules")
@Getter
@Setter
public class CourseSchedule {
    @jakarta.persistence.Id
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String building;
    private String roomNumber;
    private char dayOfWeek;
    private LocalTime startTime;
    private LocalTime endTime;

    public CourseSchedule() {}

    public CourseSchedule(String building, String roomNumber, char dayOfWeek, LocalTime startTime, LocalTime endTime) {
        this.building = building;
        this.roomNumber = roomNumber;
        this.dayOfWeek = dayOfWeek;
        this.startTime = startTime;
        this.endTime = endTime;
    }
}
